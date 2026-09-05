Project Brief: Ben Steel Website

Create a brand-new website for **Ben Steel**, a futuristic drum and bass DJ/artist brand.

**Build this project using Svelte + Vite (NOT SvelteKit).** Do NOT use plain HTML files \u2014 use Svelte components throughout.

The development version must be able to run locally at:

```txt
http://localhost:1234
```

The overall vibe should be **dark, futuristic, energetic, stylish, underground, and music-focused**, with a strong **drum and bass / rave / cyberpunk / nuclear bass** aesthetic.

---

## Core Goal

Build a complete website for **Ben Steel** from scratch using **Svelte + Vite**.

The site should feel like the digital home of a dark drum and bass DJ: stylish, intense, modern, and memorable. It should be suitable for artist promotion, party listings, DJ booking requests, and general contact.

---

## Technical Requirements

The project MUST use **Svelte + Vite** as the primary framework. Initialize with:

```bash
npm create vite@latest . -- --template svelte
```

Then add dependencies (already in the project directory):
```bash
npm install
npm install svelte-spa-router tailwindcss postcss autoprefixer --save
```

Or set up a Svelte project manually with Vite as the build tool.

A backend is optional. The first version may be fully static, as long as the forms are visually functional and ready to connect to a backend or form provider later.

The project should include:

```txt
Svelte components (.svelte files)
CSS / Tailwind styling
JavaScript where needed
Static assets folder
Responsive layout
Local development server configuration (Vite)
Clear file structure
README with setup instructions
```

The website should be runnable locally using:

```bash
npm install
npm run dev
```

The dev server must run on:

```txt
http://localhost:1234
```

Configure Vite to use port 1234 in `vite.config.js`.

---

## Styling Requirements

Use a modern styling approach such as **Tailwind CSS** or a Tailwind-inspired utility-first CSS setup.

The site should not look like a plain template. It should look custom, polished, and visually strong.

Primary colors:

```txt
Black
Blue
Dark grey
Deep navy
Neon blue accents
White or light grey text for contrast
```

The design should feel:

```txt
Futuristic
Stylish
Dark
High-energy
Underground
Premium
Music-focused
Cyberpunk-inspired
```

Use visual elements such as:

```txt
Glowing blue highlights
Dark gradients
Glassmorphism panels
Subtle animated backgrounds
Neon borders
Noise/grain texture
Bass-wave style graphics
Sharp modern typography
Smooth hover effects
Animated buttons
Responsive cards and sections
```

---

## Branding Requirements

The artist name is:

```txt
Ben Steel
```

The brand should feel like a dark drum and bass DJ identity.

Suggested tagline:

```txt
Dark Bass. Blue Energy. Future Sound.
```

### Logo Requirement

Create or include a logo concept for **Ben Steel**.

The logo must be:

```txt
A beatnological shape with a clear letter \"B\" on it
```

The logo should fit the dark futuristic drum and bass style.

Logo style direction:

```txt
Dark beatnological shape
Blue glow
Black and navy details
Clear visible \"B\" on the beatnological shape
Futuristic / cyberpunk feel
Drum and bass energy
Underground rave aesthetics
Optional nuclear / explosive bass influence
```

The homepage slider should prominently feature this **beatnological-shape-with-B logo**.

**IMAGE GENERATION FOR LOGO / HERO IMAGES**:
- Source the `.env` file for `VENICE_API_KEY` and use the Venice AI API for all image generation.
- Preferred models (in order): `seedream-v4`, `grok-imagine-image-quality`.
- If the preferred models fail, fall back to any available Venice image model.
- Image generation models reference: https://docs.venice.ai/models/image
- ONLY use Venice for image generation. Do NOT use OpenAI, DALL-E, SVG fallback, or any other image service.
- Generate actual images and save them to `src/assets/` or `public/`.

---

## Site Structure

Create a main navigation menu with the following items:

```txt
Home
About
Parties
Contact
```

The menu should be visible on all pages.

Navigation should be clean and modern, with:

```txt
Hover effects
Active page styling
Responsive mobile hamburger menu
Smooth transitions
Clear readable labels
```

The website must be responsive and work well on:

```txt
Desktop
Tablet
Mobile
```

---

# Page Requirements

## 1. Home Page

The homepage should be visually impressive and act as the main landing page.

Include:

```txt
Large hero section
Futuristic drum and bass styling
Cool animated slider / carousel
Beatnological shape logo with a B on it
Artist name: Ben Steel
Strong tagline
Call-to-action buttons
```

The slider should include at least **3 slides**.

### Slide 1

```txt
Ben Steel
Dark Bass. Blue Energy. Future Sound.
Background or main visual: beatnological-shape-with-B logo
CTA: Book Ben Steel
```

### Slide 2

```txt
Underground Drum & Bass
Explosive sets built for dark rooms, heavy rigs, and late-night energy.
CTA: View Parties
```

### Slide 3

```txt
Book the Sound
Bring Ben Steel to your next rave, club night, festival, or private event.
CTA: Contact Now
```

The homepage should also include short feature blocks, such as:

```txt
High-energy DJ sets
Dark drum and bass selections
Club, rave, and festival ready
Professional booking available
```

Add subtle animations to make the page feel alive.

Suggested effects:

```txt
Glowing logo pulse
Moving background gradients
Bass-wave animation
Slide transitions
Button hover glow
Card hover lift
```

---

## 2. About Page

Create an About page with example biography text for Ben Steel.

The text should sound professional but still fit the dark drum and bass brand.

Example biography:

```txt
Ben Steel is a drum and bass artist built for dark dancefloors, blue-lit rooms, and heavy sound systems. Blending rolling basslines, sharp breaks, and futuristic energy, Ben Steel delivers sets that move between deep, dangerous, and explosive.

With a sound rooted in underground rave culture and a taste for high-impact selections, Ben Steel brings a unique identity to every event. Expect dark atmospheres, heavy drops, and a no-compromise approach to drum and bass.
```

The page should include sections such as:

```txt
Biography
Sound & Style
Performance Energy
Booking Availability
```

Include:

```txt
Artist image placeholder
Genre tags
Quote block
Featured mixes placeholder
Stats section
Mini timeline
```

### Featured Mixes Placeholder

Add a section showcasing recent or notable DJ mixes:

```txt
A grid or list of 3-4 placeholder mixes
Each with: mix title, event/venue name, date, and a \"Listen\" link/button
Styled with dark cards and blue accent hover effects
```

Example mixes:

```txt
Steelworks Vol. 1 \u2014 Live at Blueline (2025)
Sub Frequency Guest Mix \u2014 Rotterdam Rave (2025)
Dark Rollers Special \u2014 Studio Session (2025)
Nuclear Bass Takeover \u2014 Amsterdam Underground (2024)
```

### Stats Section

Add a visual stats bar or counter section showing key numbers:

```txt
Years active: 5+
Events played: 120+
Countries: 8
Tracks released: 15+
```

These stats should be displayed as large numbers with labels, animated on scroll if possible.

### Mini Timeline

Add a short career timeline showing key milestones:

```txt
2020 \u2014 First club appearance, Rotterdam
2021 \u2014 Debut EP release on independent label
2022 \u2014 Festival debut at major Dutch events
2023 \u2014 International bookings begin (UK, Belgium, Germany)
2024 \u2014 Nuclear Bass concept launch
2025 \u2014 Steelworks residency at Blueline Amsterdam
```

The timeline should be a vertical or horizontal visual element with glowing blue markers.

Example genre tags:

```txt
Drum & Bass
Neurofunk
Dark Rollers
Jungle
Liquid Darkness
Rave Energy
```

---

## 3. Parties Page

Create a Parties page where visitors can view upcoming events and book Ben Steel as a DJ.

This page should include:

```txt
Upcoming party/event list
Event calendar section
DJ booking section
Booking request form
```

### Event Calendar Section

Add a calendar-style view or timeline showing upcoming bookings:

```txt
Visual event calendar or timeline layout
Each event shows: date, venue, city, event type, ticket link (placeholder)
Current month and next month events highlighted
Past events shown in a muted style with \"past event\" label
Styled with dark backgrounds and blue accent date markers
```

Example calendar events:

```txt
June 15, 2025 \u2014 Blueline Bass Session \u2014 Amsterdam \u2014 Club Night
July 8, 2025 \u2014 Sub Frequency Night \u2014 Rotterdam \u2014 Underground Rave
August 22, 2025 \u2014 Steelworks DNB Takeover \u2014 Utrecht \u2014 Festival Stage
September 5, 2025 \u2014 Private Booking \u2014 Hidden Location \u2014 Private Event
October 18, 2025 \u2014 Nuclear Bass \u2014 Eindhoven \u2014 Warehouse Rave
```

### Upcoming Events List

Add an upcoming events list with example events, for example:

```txt
Blueline Bass Session \u2014 Amsterdam
Sub Frequency Night \u2014 Rotterdam
Steelworks DNB Takeover \u2014 Utrecht
Private Booking \u2014 Hidden Location
```

The page should include a booking form with fields:

```txt
Name
Email
Phone number
Event name
Event date
Event location
Type of event
Expected number of guests
Message / extra details
```

The booking form should allow visitors to request Ben Steel for:

```txt
Club night
Festival
Private party
Underground rave
Corporate event
Other
```

After submission, show a friendly success message such as:

```txt
Your booking request has been received. Ben Steel will get back to you soon.
```

The form does not need to send real emails yet, but the code should be structured so real form handling can be added later.

Acceptable first-version form handling options:

```txt
Show frontend success message
Log the form data in the browser console
Use placeholder action attribute
Connect later to Formspree, Netlify Forms, custom backend, or API route
```

---

## 4. Contact Page

Create a Contact page with a clean and stylish contact form.

The contact form should include:

```txt
Name
Email
Subject
Message
```

On submit, show a confirmation message.

Example:

```txt
Thanks for reaching out. Your message has been received.
```

Also include example contact details:

```txt
Booking email: bookings@bensteel.example
Management: management@bensteel.example
Location: Netherlands / Europe
```

Add social media placeholders:

```txt
Instagram
SoundCloud
YouTube
TikTok
Mixcloud
```

The contact page should feel polished and not empty. Add supporting copy explaining that visitors can use the form for bookings, collaborations, press, or general questions.

---

## Interactivity Requirements

Add JavaScript where useful.

Expected interactive features:

```txt
Homepage slider / carousel
Mobile navigation menu
Form success messages
Smooth scroll or subtle page transitions
```

The site should remain usable even if JavaScript is minimal.

---

## Accessibility Requirements

The website should include basic accessibility best practices:

```txt
Semantic HTML5 structure
Readable color contrast
Keyboard-friendly navigation
Form labels for all inputs
Alt text for images and logo assets
Clear button text
Responsive text sizes
```

Do not rely only on color to communicate important states.

---

## Optional Bonus Features

The following features are optional but recommended to make the site stand out:

### 404 Page

```txt
A custom 404 \"Not Found\" page
Dark styled with the Ben Steel branding
A \"Return to Home\" button
Subtle bass-wave animation in the background
Fun copy like \"This track doesn't exist... yet.\"
```

### Page Loading Animation

```txt
A loading screen or transition animation on initial page load
Logo pulse or bass equalizer animation
Dark background with blue glow
Brief (1-2 second) intro animation
Smooth fade-in to the main content
```

### Newsletter Signup

```txt
A newsletter signup form (can be in the footer or as a dedicated section)
Email input field with a \"Subscribe\" button
Dark styled inline form
Placeholder for connecting to Mailchimp, ConvertKit, or similar
Success message on submission
```

### Music Player Placeholder

```txt
A floating or embedded audio player placeholder
Positioned subtly (e.g., bottom bar or sidebar widget)
Track title display area
Play/pause button styling (non-functional in first version)
Styled to match the dark blue aesthetic
Ready to embed a real SoundCloud, Mixcloud, or custom audio player
```

---

## Svelte Project File Structure

**IMPORTANT**: The project must be created DIRECTLY in the repo root (current working directory).
Do NOT create a `ben-steel-website/` subdirectory. All source files go in the repo root.
The `.qq/` subdirectory should only contain agent logs, metadata, and non-codebase artifacts.

Use a standard Svelte + Vite file structure:

```txt
repo-root/
\u2502
\u251c\u2500\u2500 package.json
\u251c\u2500\u2500 vite.config.js
\u251c\u2500\u2500 README.md
\u251c\u2500\u2500 index.html                (Vite entry point)
\u2502
\u251c\u2500\u2500 src/
\u2502   \u251c\u2500\u2500 main.js               (Svelte mount point)
\u2502   \u251c\u2500\u2500 App.svelte             (Root component with routing)
\u2502   \u251c\u2500\u2500 app.css                (Global styles)
\u2502   \u2502
\u2502   \u251c\u2500\u2500 lib/
\u2502   \u2502   \u251c\u2500\u2500 Header.svelte      (Navigation component)
\u2502   \u2502   \u251c\u2500\u2500 Footer.svelte
\u2502   \u2502   \u251c\u2500\u2500 Slider.svelte      (Homepage carousel)
\u2502   \u2502   \u251c\u2500\u2500 Logo.svelte        (Beatnological B logo component)
\u2502   \u2502   \u251c\u2500\u2500 BookingForm.svelte
\u2502   \u2502   \u2514\u2500\u2500 ContactForm.svelte
\u2502   \u2502
\u2502   \u251c\u2500\u2500 routes/
\u2502   \u2502   \u251c\u2500\u2500 Home.svelte
\u2502   \u2502   \u251c\u2500\u2500 About.svelte
\u2502   \u2502   \u251c\u2500\u2500 Parties.svelte
\u2502   \u2502   \u2514\u2500\u2500 Contact.svelte
\u2502   \u2502
\u2502   \u2514\u2500\u2500 assets/
\u2502       \u2514\u2500\u2500 (Venice-generated images stored here)
\u2502
\u2514\u2500\u2500 public/
    \u2514\u2500\u2500 favicon.png
```

Use a simple SPA router (such as svelte-spa-router) to handle page navigation.

---

## Local Development Requirement

Configure Vite so the development server runs on port **1234**.

In `vite.config.js`:

```js
import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 1234
  }
})
```

---

## README Requirements

Include a README explaining:

```txt
How to install dependencies (npm install)
How to run the development server (npm run dev)
Which URL to open (http://localhost:1234)
How the project is structured
How to customize colors, content, and images
How to replace the logo
How to connect the forms later
```

---

## Quality Expectations

The final result should:

```txt
Look stylish and professional
Use black and blue as the main colors
Feel futuristic and underground
Be fully responsive
Have working navigation
Have a homepage slider
Have an About page with biography text, featured mixes, stats, and timeline
Have a Parties page with event calendar, event list, and a DJ booking form
Have a Contact page with a working-looking contact form
Have a custom 404 page
Have a loading animation
Have a newsletter signup section
Have a music player placeholder
Show success messages after form submission
Run locally on port 1234
Use Svelte components
Use Tailwind or Tailwind-like styling
Be cleanly organized and easy to extend
Include a beatnological shape logo with a clear B on it
Use Venice AI (seedream-v4 or grok-imagine-image-quality) for all image generation
```

---

## Final Deliverable

Deliver a complete Svelte website project for **Ben Steel** that can be run locally at:

```txt
http://localhost:1234
```

The project should be created from scratch and include all source code, Svelte components, styling, JavaScript, static assets, and setup instructions.

The logo must clearly show:

```txt
A beatnological shape with a B on it
```