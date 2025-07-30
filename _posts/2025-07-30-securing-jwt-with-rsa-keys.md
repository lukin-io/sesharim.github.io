---
layout: post
title: Securing JWT Tokens in Rails API with Devise, Devise-JWT, and RSA Keys
date: 2025-07-30
<!-- description: Step-by-step guide to securing your Ruby on Rails API authentication using Devise, Devise-JWT, Doorkeeper-JWT, and RSA encryption keys. -->
author: Max Lukin
<!-- tags: [rails, jwt, devise, doorkeeper, security, rsa] -->
---

In Rails API authentication, using JWT tokens with Devise and Devise-JWT provides simplicity and efficiency. But when security requirements become stricter, shared secrets (`HS256`) may not suffice. Instead, RSA asymmetric keys (`RS256`) provide stronger cryptographic protection by separating the token issuer (private key holder) from the verifier (public key holder).

## Why RSA Keys instead of HS256?

- **Asymmetric cryptography**: Private keys sign tokens; public keys verify tokens.
- **Improved security**: Private keys remain confidential, minimizing exposure risk.
- **Scalable and maintainable**: Easily rotate keys without downtime or disruptions.

---

## Step-by-step implementation

### 1. Generate RSA key pair

First, generate an RSA key pair:

```ruby
rsa_private = OpenSSL::PKey::RSA.generate(2048)
File.write('jwt_rsa_private.pem', rsa_private.to_pem)
File.write('jwt_rsa_public.pem', rsa_private.public_key.to_pem)
```

Securely store these keys in Rails encrypted credentials (`rails credentials:edit`):

```yaml
jwt_private_key: |
  -----BEGIN RSA PRIVATE KEY-----
  your_private_key_here
  -----END RSA PRIVATE KEY-----

jwt_public_key: |
  -----BEGIN PUBLIC KEY-----
  your_public_key_here
  -----END PUBLIC KEY-----
```

### 2. Configure Devise-JWT for RS256

Update your `config/initializers/devise.rb`:

```ruby
Devise.setup do |config|
  config.jwt do |jwt|
    jwt.algorithm  = 'RS256'
    jwt.secret = OpenSSL::PKey::RSA.new(
      Rails.application.credentials.jwt_private_key
    )
    jwt.public_key = OpenSSL::PKey::RSA.new(
      Rails.application.credentials.jwt_public_key
    )
    jwt.dispatch_requests = [
      ['POST', %r{^/api/v1/sessions/sign_in$}],
      ['POST', %r{^/api/v1/users$}]
    ]
    jwt.revocation_requests = [
      ['DELETE', %r{^/api/v1/sessions/sign_out$}]
    ]
    jwt.expiration_time = 1.day.to_i
  end
end
```

### 3. Configure Doorkeeper-JWT (Optional, if using OAuth2)

Ensure Doorkeeper-JWT issues tokens using the same RSA key:

```ruby
# config/initializers/doorkeeper_jwt.rb
Doorkeeper::JWT.configure do
  token_payload do |opts|
    user = User.find(opts[:resource_owner_id])
    {
      iss: 'my-rails-api',
      sub: user.id,
      email: user.email,
      scope: opts[:scopes]
    }
  end

  secret_key OpenSSL::PKey::RSA.new(
    Rails.application.credentials.jwt_private_key
  )
  encryption_method :rs256
end
```

### 4. Verify RSA-based JWT

Your application now automatically issues and verifies JWT tokens using RSA keys. Token verification uses only the public key, keeping your private key secret and secure.

---

## Key Rotation

To rotate keys without downtime:

1. Generate a new RSA key pair.
2. Temporarily add the new public key to your application's configuration alongside the old one.
3. Issue tokens with the new private key; verify tokens with both old and new public keys.
4. After all older tokens expire, remove the old keys.

Example:

```ruby
jwt.public_key_set = [
  OpenSSL::PKey::RSA.new(new_public_key),
  OpenSSL::PKey::RSA.new(old_public_key)
]
```

---

## Test via cURL

Sign-in example:

```bash
curl -X POST http://localhost:3000/api/v1/sessions/sign_in \
-H "Content-Type: application/json" \
-d '{"user":{"email":"alice@example.com","password":"password123"}}'
```

The response includes an RSA-signed JWT:

```
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
```

---

**Conclusion**

Switching to RSA keys (`RS256`) strengthens JWT token security in your Rails API, clearly separating token generation and verification responsibilities and simplifying key management at scale.
