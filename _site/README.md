# lukin.io

Personal website built with Jekyll and Tailwind CSS.

## Setup

### Prerequisites

- **Ruby 3.4.4** (or compatible version)
- **Node.js 20+** and npm
- **Bundler** gem

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd lukin_io
   ```

2. **Install Ruby dependencies:**
   ```bash
   bundle install
   ```

3. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

4. **Build CSS (required before running Jekyll):**
   ```bash
   npm run build:css
   ```

## Development

### Local Development

1. **Build CSS (one-time, or in watch mode):**
   ```bash
   # Build once
   npm run build:css

   # Watch for changes (in separate terminal)
   npm run watch:css
   ```

2. **Serve Jekyll site:**
   ```bash
   # Option 1: Build CSS then serve (recommended)
   npm run jekyll:serve

   # Option 2: Manual (if CSS is already built)
   bundle exec jekyll serve
   ```

3. **Visit:** `http://localhost:4000`

### Building for Production

```bash
# Build CSS and Jekyll site
npm run jekyll:build
```

Or manually:
```bash
npm run build:css
bundle exec jekyll build
```

## Troubleshooting

### CSS not building

If you get `postcss: command not found`, make sure you've installed npm dependencies:
```bash
npm install
```

### Clean build

To start fresh:
```bash
# Clean Jekyll cache and build artifacts
bundle exec jekyll clean

# Remove node_modules and reinstall (if needed)
rm -rf node_modules package-lock.json
npm install

# Rebuild CSS
npm run build:css
```

## Deployment

The site is automatically deployed to GitHub Pages via GitHub Actions when changes are pushed to the `master` branch.

The CI pipeline:
1. Sets up Ruby and Node.js environments
2. Installs Ruby dependencies (Bundler)
3. Installs Node.js dependencies (npm)
4. Builds CSS using PostCSS/Tailwind
5. Builds Jekyll site
6. Deploys to GitHub Pages

## Project Structure

- `assets/css/tailwind.css` - Tailwind source file
- `assets/css/styles.css` - Compiled CSS (generated, don't edit)
- `_layouts/` - Jekyll layouts
- `_posts/` - Blog posts
- `.github/workflows/deploy.yml` - CI/CD configuration

## Technologies

- **Jekyll** - Static site generator
- **Tailwind CSS** - Utility-first CSS framework
- **PostCSS** - CSS processing
- **GitHub Pages** - Hosting
