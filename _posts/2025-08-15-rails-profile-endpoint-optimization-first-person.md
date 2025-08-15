---
layout: post
author: Max Lukin
title: Optimizing a Complex Rails Profile Endpoint — my step‑by‑step notes
date: 2025-08-15 09:00:00
tags: [rails-8, rack, healthcheck, devops, reliability]
categories: rails performance api optimization blueprinter ransack caching
excerpt: Optimizing a Complex Rails Profile Endpoint
---

I had an API endpoint that returned a **Profile** and a lot of nested associations. It worked, but the shape of the data made it easy to trigger N+1s or force a single **monster JOIN** that Postgres struggled to optimize.

This write‑up is my engineering log: what I started with, why it was slow, and the exact changes I shipped. It includes **every example from the session**, starting at **1)**, along with the full SQL log and the original preload code. All snippets are explicitly file‑scoped so they’re copy‑pasteable into a Rails 7/8 codebase.

---

## 1) Baseline & symptoms

**Endpoint:**

- `GET /api/v1/profiles/:id` (show)
- `GET /api/v1/profiles` (index with Ransack filters + pagination)

**Real SQL log I started from (show):**

```text
Started GET "/api/v1/profiles/1" for ::1 at 2025-08-11 14:59:59 +0000
Processing by Api::V1::ProfilesController#show as */*
  Parameters: {"id" => "1"}
  User Load (15.4ms)  SELECT `users`.* FROM `users` WHERE `users`.`id` = 1 LIMIT 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  Profile Load (0.2ms)  SELECT `profiles`.* FROM `profiles` WHERE `profiles`.`id` = 1 LIMIT 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:143:in 'Api::V1::ProfilesController#set_profile'
  AwardItem Load (0.3ms)  SELECT `award_items`.* FROM `award_items` WHERE `award_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  CertificationItem Load (0.3ms)  SELECT `certification_items`.* FROM `certification_items` WHERE `certification_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  ContactInfo Load (0.2ms)  SELECT `contact_infos`.* FROM `contact_infos` WHERE `contact_infos`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  ContentBlock Load (0.2ms)  SELECT `content_blocks`.* FROM `content_blocks` WHERE `content_blocks`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  EducationItem Load (0.2ms)  SELECT `education_items`.* FROM `education_items` WHERE `education_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  FileDocument Load (0.8ms)  SELECT `attachments`.* FROM `attachments` WHERE `attachments`.`type` = 'FileDocument' AND `attachments`.`attachable_id` = 1 AND `attachments`.`attachable_type` = 'Profile' /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  HighlightLink Load (0.3ms)  SELECT `highlight_links`.* FROM `highlight_links` WHERE `highlight_links`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  GalleryImage Load (0.2ms)  SELECT `attachments`.* FROM `attachments` WHERE `attachments`.`type` = 'GalleryImage' AND `attachments`.`attachable_id` = 1 AND `attachments`.`attachable_type` = 'Profile' /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  Language Load (0.2ms)  SELECT `languages`.* FROM `languages` WHERE `languages`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  LicenseItem Load (0.2ms)  SELECT `license_items`.* FROM `license_items` WHERE `license_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  LocationSetting Load (0.2ms)  SELECT `location_settings`.* FROM `location_settings` WHERE `location_settings`.`profile_id` = 1 LIMIT 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  PortfolioLink Load (0.3ms)  SELECT `portfolio_links`.* FROM `portfolio_links` WHERE `portfolio_links`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  ProjectItem Load (0.2ms)  SELECT `project_items`.* FROM `project_items` WHERE `project_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  FileDocument Load (0.2ms)  SELECT `attachments`.* FROM `attachments` WHERE `attachments`.`type` = 'FileDocument' AND `attachments`.`attachable_id` = 1 AND `attachments`.`attachable_type` = 'ProjectItem' /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  GalleryImage Load (0.2ms)  SELECT `attachments`.* FROM `attachments` WHERE `attachments`.`type` = 'GalleryImage' AND `attachments`.`attachable_id` = 1 AND `attachments`.`attachable_type` = 'ProjectItem' /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  Resume Load (0.2ms)  SELECT `resumes`.* FROM `resumes` WHERE `resumes`.`profile_id` = 1 LIMIT 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  FileDocument Load (0.2ms)  SELECT `attachments`.* FROM `attachments` WHERE `attachments`.`type` = 'FileDocument' AND `attachments`.`attachable_id` = 1 AND `attachments`.`attachable_type` = 'Resume' /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  SalaryExpectation Load (0.3ms)  SELECT `salary_expectations`.* FROM `salary_expectations` WHERE `salary_expectations`.`profile_id` = 1 LIMIT 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  SecurityClearanceItem Load (0.2ms)  SELECT `security_clearance_items`.* FROM `security_clearance_items` WHERE `security_clearance_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  SkillReview Load (0.2ms)  SELECT `skill_reviews`.* FROM `skill_reviews` WHERE `skill_reviews`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  Skill Load (0.2ms)  SELECT `skills`.* FROM `skills` WHERE `skills`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  VolunteerWorkItem Load (0.2ms)  SELECT `volunteer_work_items`.* FROM `volunteer_work_items` WHERE `volunteer_work_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  WorkExperience Load (0.2ms)  SELECT `work_experiences`.* FROM `work_experiences` WHERE `work_experiences`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  WorkReference Load (0.2ms)  SELECT `work_references`.* FROM `work_references` WHERE `work_references`.`work_experience_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
  WorkingKnowledgeItem Load (0.2ms)  SELECT `working_knowledge_items`.* FROM `working_knowledge_items` WHERE `working_knowledge_items`.`profile_id` = 1 /*action='show',application='WigiworkBack',controller='profiles'*/
  ↳ app/controllers/api/v1/profiles_controller.rb:109:in 'Api::V1::ProfilesController#show'
Completed 200 OK in 46ms (Views: 0.3ms | ActiveRecord: 22.0ms (27 queries, 0 cached) | GC: 1.4ms)
```

**Original preload block (index) I wanted to replace:**

```ruby
# app/controllers/api/v1/profiles_controller.rb (index; BEFORE)
@profiles = Profile.preload(
  :user,
  :contact_infos,
  :skills,
  :work_experiences,
  :portfolio_links,
  :languages,
  :content_blocks,
  :skill_reviews,
  :education_items,
  :working_knowledge_items,
  :certification_items,
  :award_items,
  :project_items,
  :highlight_links,
  :security_clearance_items,
  :license_items,
  :images,
  :files,
  :location_setting,
  :salary_expectation,
  # Nested associations for models that have their own associations
  { certification_items: [:files] },
  { resume: [:files] },
  { work_experiences: :work_references },
  { education_items: [:images, :files] },
  { license_items: [:images, :files, :license_links] },
  { project_items: [:images, :files] },
  { volunteer_work_items: [:images, :files] },
  { award_items: [:files] },
  # { security_clearance_items: [:images, :files] },
  # { certification_items: [:images, :files] },
  # { working_knowledge_items: [:images, :files] }
)
.ransack(ransack_params)
.result(distinct: true)
.page(params[:page])
.per(params[:limit])
```

This fetches **everything** by default. Even when the UI only needed a subset, the DB and the JSON renderer were doing unnecessary work.

---

## 2) I made the payload **opt‑in** via `include=` and `fields=`

I added a small concern to parse and **whitelist** expansions and sparse fieldsets.

**File:** `app/controllers/concerns/include_params.rb`

```ruby
module IncludeParams
  # Whitelist to avoid arbitrary preload trees
  ALLOWED_INCLUDES = %w[
    user contact_infos skills work_experiences.work_references portfolio_links
    languages content_blocks skill_reviews education_items.images education_items.files
    working_knowledge_items certification_items.files award_items.files
    project_items.images project_items.files highlight_links security_clearance_items
    license_items.images license_items.files license_items.license_links
    images files resume.files location_setting salary_expectation volunteer_work_items.images
    volunteer_work_items.files
  ].freeze

  def parsed_includes
    raw = params[:include].to_s.split(',').map(&:strip)
    raw & ALLOWED_INCLUDES
  end

  # JSON:API-style sparse fieldsets, e.g. fields[profiles]=id,username,role
  def parsed_fields
    fields = params.fetch(:fields, {}).to_h.transform_values { |v| v.split(',').map(&:strip) }
    fields.transform_keys!(&:to_s)
  end
end
```

**How I call it:**

- `GET /api/v1/profiles/1` → **compact** default payload.
- `GET /api/v1/profiles/1?include=project_items.images,education_items.files` → only those heavy bits are expanded.

---

## 3) Controller changes: **preload for rendering, JOIN for filters**

I mapped `include` tokens to a preload tree, and I only `JOIN` on associations that Ransack actually filters or sorts on.

**File:** `app/controllers/api/v1/profiles_controller.rb`

```ruby
class Api::V1::ProfilesController < ApplicationController
  include IncludeParams

  # Map requested include tokens to a preload tree
  PRELOAD_MAP = {
    'user' => :user,
    'contact_infos' => :contact_infos,
    'skills' => :skills,
    'work_experiences' => { work_experiences: :work_references },
    'portfolio_links' => :portfolio_links,
    'languages' => :languages,
    'content_blocks' => :content_blocks,
    'skill_reviews' => :skill_reviews,
    'education_items.images' => { education_items: :images },
    'education_items.files'  => { education_items: :files },
    'working_knowledge_items' => :working_knowledge_items,
    'certification_items.files' => { certification_items: :files },
    'award_items.files' => { award_items: :files },
    'project_items.images' => { project_items: :images },
    'project_items.files'  => { project_items: :files },
    'highlight_links' => :highlight_links,
    'security_clearance_items' => :security_clearance_items,
    'license_items.images' => { license_items: :images },
    'license_items.files'  => { license_items: :files },
    'license_items.license_links' => { license_items: :license_links },
    'images' => :images,
    'files'  => :files,
    'resume.files' => { resume: :files },
    'location_setting' => :location_setting,
    'salary_expectation' => :salary_expectation,
    'volunteer_work_items.images' => { volunteer_work_items: :images },
    'volunteer_work_items.files'  => { volunteer_work_items: :files }
  }.freeze

  # GET /api/v1/profiles
  def index
    includes = parsed_includes
    fields   = parsed_fields
    scope    = Profile.all

    # JOINs strictly for Ransack filters/sorts.
    if params.dig(:q)&.keys&.any? { |k| k.start_with?('user_') }
      scope = scope.joins(:user)
    end
    if params.dig(:q)&.keys&.any? { |k| k.start_with?('location_setting_') }
      scope = scope.joins(:location_setting)
    end

    scope = scope.preload(preload_tree(includes)) if includes.any?

    records = scope.ransack(ransack_params).result(distinct: true)
                   .page(params[:page]).per(params[:limit])

    render json: ProfileBlueprint.render(records,
      view: view_for(includes),
      fields: fields['profiles'])
  end

  # GET /api/v1/profiles/:id
  def show
    includes = parsed_includes
    fields   = parsed_fields

    scope = Profile.preload(preload_tree(includes))
    @profile = scope.find(params[:id])

    # Strong HTTP caching: ETag + Last-Modified across key associations
    last_mod = [
      @profile.updated_at,
      @profile.skills.maximum(:updated_at),
      @profile.work_experiences.maximum(:updated_at)
    ].compact.max

    fresh_when etag: [@profile.cache_key_with_version, includes.sort],
               last_modified: last_mod,
               public: true

    render json: ProfileBlueprint.render(@profile,
      view: view_for(includes),
      fields: fields['profiles'])
  end

  private

  def preload_tree(includes)
    includes.map { |key| PRELOAD_MAP.fetch(key) }
  end

  def view_for(includes)
    if includes.any? { |i| i.start_with?('project_items') || i.start_with?('education_items') }
      :extended
    elsif includes.any?
      :standard
    else
      :compact
    end
  end

  def ransack_params
    params.fetch(:q, {})
  end
end
```

---

## 4) Serializer views + per‑record caches (Blueprinter)

The default is **compact**; heavier trees are behind `:standard` and `:extended`. Heavy leaf nodes cache by `cache_key_with_version`.

**File:** `app/blueprints/profile_blueprint.rb`

```ruby
class ProfileBlueprint < Blueprinter::Base
  identifier :id

  view :compact do
    fields :username, :role, :location, :experience_years
    association :user, blueprint: UserBlueprint, view: :tiny
  end

  view :standard do
    include_view :compact
    association :skills, blueprint: SkillBlueprint
    association :languages, blueprint: LanguageBlueprint
  end

  view :extended do
    include_view :standard
    association :work_experiences, blueprint: WorkExperienceBlueprint, view: :with_refs
    association :education_items, blueprint: EducationItemBlueprint, view: :with_assets
    association :project_items, blueprint: ProjectItemBlueprint, view: :with_assets do |profile, options|
      max = options[:locals]&.fetch(:max_children, 25)
      profile.project_items.limit(max)
    end
    association :license_items, blueprint: LicenseItemBlueprint, view: :with_assets
    association :resume, blueprint: ResumeBlueprint, view: :with_files
  end
end
```

**File:** `app/blueprints/project_item_blueprint.rb`

```ruby
class ProjectItemBlueprint < Blueprinter::Base
  identifier :id
  fields :title, :summary, :started_on, :finished_on

  association :images, blueprint: AttachmentBlueprint
  association :files,  blueprint: AttachmentBlueprint

  # Per-record cache
  cache ->(obj, _opts) { "bp:project_item:#{obj.cache_key_with_version}" }
end
```

---

## 5) Avoid “monster SQL”: split JOINs for filters from PRELOADs for rendering

This is the pattern I keep handy when the index endpoint starts accreting conditions:

```ruby
scope = Profile.all

joins_needed = []
joins_needed << :user if params.dig(:q)&.keys&.any? { |k| k.start_with?('user_') }
joins_needed << :location_setting if params.dig(:q)&.keys&.any? { |k| k.start_with?('location_setting_') }
scope = scope.joins(*joins_needed) if joins_needed.any?

scope = scope.preload(preload_tree(parsed_includes))
records = scope.ransack(ransack_params).result(distinct: true)
```

---

## 6) Async preloading (optional)

Rails 7/8 lets me parallelize independent SELECTs:

**File:** `config/application.rb`

```ruby
config.active_record.async_query_executor = :global_thread_pool
config.active_record.global_executor_concurrency = 4 # tune per env
```

**Usage (example):**

```ruby
@profile = Profile.preload(preload_tree(parsed_includes)).load_async.find(params[:id])
```

---

## 7) Cap / paginate heavy nested collections

I pass a `locals` cap to Blueprinter and enforce it in the association (see `ProfileBlueprint` above).

```ruby
# app/controllers/api/v1/profiles_controller.rb (show)
render json: ProfileBlueprint.render(@profile, view: :extended, locals: { max_children: 25 })
```

---

## 8) Side‑loading for fastest TTFB

Sometimes I just want IDs first, details later.

**Main payload sideload IDs:**

```json
{
  "id": 1,
  "project_item_ids": [3,5,8,13]
}
```

**Then fetch details in bulk:**

```
GET /api/v1/project_items?ids=3,5,8,13
```

**Or expose a focused associations endpoint:**

**File:** `app/controllers/api/v1/profile_associations_controller.rb`

```ruby
class Api::V1::ProfileAssociationsController < ApplicationController
  include IncludeParams

  def show
    profile = Profile.find(params[:id])
    includes = parsed_includes
    raise ActionController::BadRequest, "include= required" if includes.blank?

    # Preload requested bits only
    Profile.where(id: profile.id).preload(preload_tree(includes)).load

    render json: {
      id: profile.id,
      include: includes,
      data: ProfileBlueprint.render(profile, view: :extended, fields: params.dig(:fields, 'profiles'))
    }
  end

  private

  def preload_tree(includes)
    includes.map { |key| Api::V1::ProfilesController::PRELOAD_MAP.fetch(key) }
  end
end
```

Usage:

```
GET /api/v1/profiles/1/associations?include=project_items,education_items
```

---

## 9) Model‑level tweaks that prevent surprise queries

**File:** `app/models/profile.rb`

```ruby
class Profile < ApplicationRecord
  has_many :skills, inverse_of: :profile, dependent: :destroy
  has_many :project_items, inverse_of: :profile, dependent: :destroy
  # If you use counters a lot:
  # has_many :work_experiences, inverse_of: :profile, dependent: :destroy, counter_cache: true
end
```

I also use `touch: false` on high‑churn relations so I don’t constantly invalidate parent caches.

To keep Ransack from auto‑joining unexpected stuff, I whitelist:

```ruby
# app/models/profile.rb
def self.ransackable_associations(_ = nil)
  %w[user location_setting]
end

def self.ransackable_attributes(_ = nil)
  %w[username role location experience_years]
end
```

---

## 10) Guardrails: I enforce a “query budget” in tests

**File:** `spec/requests/api/v1/profiles_spec.rb`

```ruby
it 'stays under 12 queries for compact show' do
  expect {
    get "/api/v1/profiles/#{profile.id}"
  }.to make_database_queries(count: <= 12) # adapt matcher/threshold
end
```

I also log `payload_size` (bytes) and render time so regressions show up in metrics, not in user reports.

---

## 11) Requests I actually run during development

**Index (lean default):**

```
GET /api/v1/profiles?page=1&limit=20
```

**Index + filter on user + expand a bit:**

```
GET /api/v1/profiles?include=skills,languages&q[user_email_cont]=max@
```

**Show minimal (fastest):**

```
GET /api/v1/profiles/1
```

**Show with heavy expansions:**

```
GET /api/v1/profiles/1?include=project_items.images,education_items.files,license_items.files
```

**Fetch only associations later:**

```
GET /api/v1/profiles/1/associations?include=project_items,education_items
```

---

## 12) Appendix — the full “before” preload list (for posterity)

```ruby
Profile.preload(
  :user,
  :contact_infos,
  :skills,
  :work_experiences,
  :portfolio_links,
  :languages,
  :content_blocks,
  :skill_reviews,
  :education_items,
  :working_knowledge_items,
  :certification_items,
  :award_items,
  :project_items,
  :highlight_links,
  :security_clearance_items,
  :license_items,
  :images,
  :files,
  :location_setting,
  :salary_expectation,
  { certification_items: [:files] },
  { resume: [:files] },
  { work_experiences: :work_references },
  { education_items: [:images, :files] },
  { license_items: [:images, :files, :license_links] },
  { project_items: [:images, :files] },
  { volunteer_work_items: [:images, :files] },
  { award_items: [:files] }
)
```

---

### What changed (in one screen)

- Default response is **compact**; clients expand with `include=`/`fields=`.
- I **JOIN** only for filters/sorts; I **preload** what I render.
- Heavier serializer views are cached per record.
- Strong **ETag/Last‑Modified** avoids re‑rendering unchanged resources.
- Optional **async preloading** helps when many independent associations exist.
- I cap/paginate heavy children or fetch them via dedicated endpoints.
- Guardrails (query budget, Ransack whitelists, payload logging) keep it fast.

If you drop this post into a Jekyll site, name it `_posts/2025-08-15-rails-profile-endpoint-optimization.md`.
