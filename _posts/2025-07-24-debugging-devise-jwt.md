---
title: "From 401s to JWT Bliss: Debugging Devise‑JWT on a Rails 8 API‑only App"
date: 2025-07-24
description: >
  A step‑by‑step log of the dead‑ends and the final, tidy setup—
  complete with code snippets, failure‑app JSON errors, and cURL recipes.
tags: [rails, devise, jwt, api, debugging]
---

> *“Postman logs me in, cURL gives ‘You need to sign in’, and somehow
> I can hit endpoints with **no** token at all—what on earth is going on?”*

I spent two days chasing those puzzles.
Below is everything I learned, condensed into one checklist you can drop
into your own Rails 8 API‑only project.

## Table of contents

1. [Gemfile & migration](#1-gemfile--migration)
2. [User model with `JTIMatcher`](#2-user-model-jtirevocation)
3. [JWT‑aware `devise.rb`](#3-devise-initializer)
4. [Failure app for uniform 401 JSON](#4-json-failure-app)
5. [Routes in *one* line](#5-single-devisefor-line)
6. [ApplicationController guard](#6-authenticate-user)
7. [Custom Sessions & Registrations controllers](#7-controllers)
8. [cURL cookbook](#8-curl-cookbook)
9. [Common pitfalls & their fixes](#9-pitfalls)

---

## 1  Gemfile & migration <a name="1-gemfile--migration"></a>

```ruby
# Gemfile
gem 'devise'
gem 'devise-jwt'
```

```bash
bundle install
```

`db/migrate/xxxx_add_jti_to_users.rb`

```ruby
class AddJtiToUsers < ActiveRecord::Migration[7.1]
  def change
    add_column :users, :jti, :string, null: false, default: -> { 'gen_random_uuid()' }
    add_index  :users, :jti, unique: true
  end
end
```

```bash
rails db:migrate
```

---

## 2  User model + JTI revocation <a name="2-user-model-jtirevocation"></a>

```ruby
class User < ApplicationRecord
  devise :database_authenticatable, :registerable,
         :jwt_authenticatable, jwt_revocation_strategy: self

  include Devise::JWT::RevocationStrategies::JTIMatcher

  def self.jwt_revoked?(payload, user)
    user.jti != payload['jti']
  end

  def self.revoke_jwt(_payload, user)
    Rails.logger.debug 'revoke_jwt TRIGGERED'
    user.update_column(:jti, SecureRandom.uuid)
  end
end
```

---

## 3  Devise initializer <a name="3-devise-initializer"></a>

```ruby
Devise.setup do |config|
  config.skip_session_storage = [:http_auth, :params_auth, :token_auth, :cookie]
  config.navigational_formats = []

  config.jwt do |jwt|
    jwt.secret = Rails.application.credentials.devise_jwt_secret_key
    jwt.dispatch_requests = [
      ['POST', %r{^/api/v1/sessions/sign_in$}],
      ['POST', %r{^/api/v1/users$}]
    ]
    jwt.revocation_requests = [
      ['DELETE', %r{^/api/v1/sessions/sign_out$}]
    ]
    jwt.expiration_time = 1.day.to_i
  end

  config.warden do |manager|
    manager.failure_app = ApiFailureApp
  end
end
```

---

## 4  JSON failure app <a name="4-json-failure-app"></a>

```ruby
class ApiFailureApp < Devise::FailureApp
  def respond
    self.status        = 401
    self.content_type  = 'application/json'
    self.response_body = {
      error: {
        code:    'UNAUTHORIZED',
        message: 'Invalid or missing JWT token'
      }
    }.to_json
  end
end
```

---

## 5  Single `devise_for` line (keeps mapping `:user`) <a name="5-single-devisefor-line"></a>

```ruby
Rails.application.routes.draw do
  devise_for :users,
             path: 'api/v1',
             path_names: {
               sign_in:  'sessions/sign_in',
               sign_out: 'sessions/sign_out',
               registration: 'users'
             },
             controllers: {
               sessions:      'api/v1/sessions',
               registrations: 'api/v1/registrations'
             }

  namespace :api do
    namespace :v1 do
      resources :users
      # … other resources …
    end
  end
end
```

Run `rails r 'puts Devise.mappings.keys'` → `[:user]`.

---

## 6  Application‑wide guard <a name="6-authenticate-user"></a>

```ruby
class ApplicationController < ActionController::API
  include Devise::Controllers::Helpers

  before_action :authenticate_user!, unless: :devise_controller?

  rescue_from JWT::DecodeError, with: :render_unauthorized

  private

  def render_unauthorized(_e = nil)
    render json: { error: { code: 'UNAUTHORIZED',
                            message: 'Invalid or missing JWT token' } },
           status: :unauthorized
  end
end
```

---

## 7  Controllers <a name="7-controllers"></a>

### Sessions

```ruby
module Api
  module V1
    class SessionsController < Devise::SessionsController
      respond_to :json
      wrap_parameters false
      skip_before_action :verify_signed_out_user, only: :destroy

      def respond_with(resource, _opts = {})
        render json: {
          message: 'Logged in successfully.',
          user:    { id: resource.id, email: resource.email }
        }, status: :ok
      end

      def respond_to_on_destroy
        render json: { status: 200, message: 'Logged out successfully.' }
      end
    end
  end
end
```

### Registrations (no auto‑login)

```ruby
module Api
  module V1
    class RegistrationsController < Devise::RegistrationsController
      respond_to :json
      wrap_parameters false

      def sign_up(_scope, _resource); end # skip auto-login

      private

      def respond_with(resource, _opts = {})
        if resource.persisted?
          render json: {
            message: 'Signed up successfully.',
            user:    { email: resource.email }
          }, status: :ok
        else
          render json: { errors: resource.errors.full_messages },
                 status: :unprocessable_entity
        end
      end

      def sign_up_params
        params.require(:user)
              .permit(:email, :password, :password_confirmation)
      end
    end
  end
end
```

---

## 8  cURL cookbook <a name="8-curl-cookbook"></a>

```bash
# Sign‑up
curl -X POST http://localhost:3000/api/v1/users   -H "Content-Type: application/json"   -d '{"user":{"email":"alice@example.com",
               "password":"password123",
               "password_confirmation":"password123"}}'

# Sign‑in
curl -X POST http://localhost:3000/api/v1/sessions/sign_in   -H "Content-Type: application/json"   -d '{"user":{"email":"alice@example.com","password":"password123"}}' -i
# (copy token from Authorization header)

# Protected endpoint
curl http://localhost:3000/api/v1/users   -H "Authorization: Bearer <TOKEN>"

# Sign‑out
curl -X DELETE http://localhost:3000/api/v1/sessions/sign_out   -H "Authorization: Bearer <TOKEN>"

# Token now invalid
curl http://localhost:3000/api/v1/users   -H "Authorization: Bearer <TOKEN>"
```

---

## 9  Pitfalls & fixes <a name="9-pitfalls"></a>

* **Mapping key mismatch** → check `Devise.mappings.keys`.
  `[:user]` means helpers are `authenticate_user!`.
  Anything else means you must call `authenticate_<scope>_user!`.

* **Postman works, cURL fails** → Postman was sending a cookie session.
  Fix: `skip_session_storage = [:cookie]`.

* **Double‑slash paths block JWT dispatch** → use `path: 'api/v1'`
  (no leading `/`) and update regexes.

* **“Not enough or too many segments”** → handled by failure app +
  `rescue_from JWT::DecodeError`.

And that’s all: Rails 8 + Devise + JWT, with uniform JSON errors,
cookie‑free, and cURL‑/Postman‑compatible.
