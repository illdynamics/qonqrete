# QonQrete Live Proof Task 04

## Goal

Create a clearly beefier application than the earlier proof tasks so that a first pass is likely to miss something, making this a strong test of bounded repair/continuation behavior.

The target is not chaos. The target is a medium-complexity app with enough moving parts that at least one repair pass is likely to be needed.

## Task

Build a tiny **single-page recipe planner** using plain HTML, CSS, and JavaScript.

The app must help a user store recipes, search them, filter them, favorite them, and generate a simple weekly meal plan from the saved recipes.

The project must contain exactly these files:

- `index.html`
- `styles.css`
- `app.js`

## Functional Requirements

### Layout
The page must include:

- main title: `QonQrete Recipe Planner`
- short subtitle: `Repair/continuation proof demo`
- a recipe creation form with:
  - recipe name input
  - multiline ingredients textarea
  - multiline steps textarea
  - category select with exactly these options:
    - `Breakfast`
    - `Lunch`
    - `Dinner`
    - `Snack`
- an **Add Recipe** button
- a search input
- a category filter with:
  - `All`
  - `Breakfast`
  - `Lunch`
  - `Dinner`
  - `Snack`
- a favorites-only toggle
- a recipe list/grid area
- a weekly meal-plan area
- a stats area showing:
  - total recipes
  - visible recipes
  - favorite recipes
  - planned slots filled

### Recipe behavior
Each recipe must support:

- create a recipe
- delete a recipe
- favorite / unfavorite a recipe
- expand / collapse long sections
- display:
  - name
  - ingredients
  - steps
  - category
  - favorite state

### Validation behavior
- do not allow empty recipe names
- do not allow empty ingredients
- do not allow empty steps
- trim surrounding whitespace before saving
- if any required field is empty after trimming, do not add the recipe

### Search and filtering
- search must filter recipes by:
  - name
  - ingredients
  - steps
- category filter must work together with search
- favorites-only toggle must work together with both
- all filtering must update visible recipes immediately

### Sorting
Visible recipes must be shown in this order:

1. favorited recipes first
2. within the same favorite state, newest first

### Weekly meal plan
The meal-plan area must support exactly these seven slots:

- Monday
- Tuesday
- Wednesday
- Thursday
- Friday
- Saturday
- Sunday

For each day, the user must be able to:

- assign one saved recipe to that day
- clear the assigned recipe for that day

The weekly plan must update immediately.

### Persistence
Use `localStorage` and exactly these keys:

- `qonqrete-recipe-planner-recipes`
- `qonqrete-recipe-planner-plan`

### Empty states
The UI must show a clear empty-state message when:
- there are no recipes at all
- no recipes match the current search/filter state

## Visual Requirements

- keep the layout clean and readable
- make recipe cards visually separated
- favorite state must be visibly distinct
- expanded/collapsed state must be obvious
- meal-plan area must be clearly separated from the recipe list
- do not use external libraries, fonts, icons, or assets

## Technical Constraints

- use plain HTML, CSS, and vanilla JavaScript only
- no frameworks
- no package manager
- no build tooling
- no TypeScript
- no backend
- no external network requests
- no extra files
- no README unless the system absolutely requires one
- keep the implementation readable and reasonably compact

## Data Model Requirements

Each stored recipe must contain exactly these fields:

- `id`
- `name`
- `ingredients`
- `steps`
- `category`
- `favorite`
- `createdAt`

Do not add extra fields.

The weekly plan must map each day name to either:
- a recipe `id`, or
- `null`

Do not invent extra plan metadata.

## Strict Scope Rules

- only implement what is explicitly described here
- do not add editing
- do not add drag-and-drop
- do not add import/export
- do not add nutrition data
- do not add tags beyond the category field
- do not add pagination
- do not add themes
- do not add animations
- do not invent extra features

## Why this task is intentionally beefier

This app has:
- multiple coordinated UI areas
- two localStorage domains
- several interacting filters
- derived stats
- cross-linked meal-plan assignment
- stricter state/render consistency requirements

That makes it a better stress test for whether QonQrete can continue in bounded fashion until the task is actually finished.

## Completion Criteria

- the repo root contains:
  - `index.html`
  - `styles.css`
  - `app.js`
- opening `index.html` in a browser provides a working recipe planner
- creating, deleting, favoriting, searching, filtering, and persistence all work
- meal-plan assignment and clearing work across all seven days
- stats update correctly
- the app remains within strict scope and does not add extra features
