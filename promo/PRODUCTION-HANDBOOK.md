# Lokalo Motion Production System

**Status:** canonical internal handbook  
**Scope:** every Lokalo commercial, launch film, product film, feature film, social cut-down, keynote segment, and marketing animation.  
**Implementation platform:** Remotion.  
**Creative register:** Lokalo Noir: precise, calm, dark, operational, tactile. This is marketing language, not the product UI design system.

---

## 1. Operating Charter

### Philosophy

This system produces evidence-led films, not advertisements dressed up as product footage. A Lokalo production earns attention by showing a true operational tension, making the product's action legible, and allowing the result to land. It should feel inevitable, composed, and expensive because every image, cut, movement, and sound has a job.

The viewer must never need to decode a visual trick to understand the product. Beauty is a delivery mechanism for clarity. Restraint is not a lack of ambition; it is the discipline of spending emphasis only where the story needs it.

### Goals

- Make the audience feel that Lokalo understands restaurant operations from the inside.
- Show specific outcomes, not generic claims, decorative dashboards, or fictional growth charts.
- Give each frame one dominant read: feeling, fact, action, proof, or brand.
- Build sequences that are reusable, configurable, deterministic, and reviewable frame by frame.
- Make sound and picture one authored experience.

### Non-negotiables

1. Begin with the audience's operational reality, not a feature inventory.
2. Product footage must depict an available, honest state. Use labeled concepts when a future state is essential.
3. Motion explains causality, hierarchy, change, focus, or material. If it does none, remove it.
4. A scene may contain one primary visual event and at most one supporting event at a time.
5. Do not use decorative gradients, unexplained particles, bokeh, generic 3D objects, faux terminal code, random metric counters, or fast-cut noise as a substitute for an idea.
6. Never make the audience wait for a reveal that delivers less information than a cut would.
7. Every production has a reduced-motion review and an accessibility-safe alternate presentation where applicable.

### Quality checklist

- [ ] The core promise is expressible in one concrete sentence.
- [ ] Every claim has a visual proof, a product proof, or is removed.
- [ ] The film works without narration, then improves with narration.
- [ ] The final logo holds long enough to be encoded, without becoming a dead end.
- [ ] No shot remains because it was difficult to make.

---

## 2. Authority, Skills, and Decision Order

### Required skill protocol

Before producing or materially revising a Remotion film, invoke available skills in this order:

1. `remotion-best-practices` / Remotion Skill: rendering, sequencing, props, media, performance, and deterministic implementation.
2. `emil-design-eng`: whether a motion decision should exist, then its invisible craft details.
3. `review-animations`: independent motion audit before approval.
4. `design-motion-principles`: timing, orchestration, accessibility, and anti-pattern audit.
5. `Taste`: composition, selection, editorial judgment, and avoidance of generic visual solutions.
6. `Impeccable`: visual hierarchy, typography, spacing, contrast, and polish audit.
7. `UI UX Pro Max`: product-state accuracy, comprehensibility, and interface ergonomics.

When a named skill is unavailable, state that fact in the production log and apply its role manually. Do not substitute a tool's output for judgment.

### Conflict resolution

For motion or UI-animation decisions, resolve disagreement in this order:

1. Emil Kowalski's restraint and purpose test.
2. Apple motion guidance: purposeful, brief, legible, optional, and comfortable.
3. Design Motion Principles.
4. Other skill or library guidance.

For product truth, current product owner decisions and live product behavior override every creative preference. For brand, current Lokalo marketing direction overrides references and historical assets.

### Production log

Each job has `production.json` or a matching production brief recording: project name, owner, objective, audience, message hierarchy, source-of-truth product build, approval status, aspect ratios, fps, delivery codecs, rights status, music license, reviewer decisions, and render hashes.

---

## 3. Research Synthesis and Reference Standard

### What to learn, not copy

Apple's motion guidance establishes the baseline: use motion purposefully, make feedback brief and precise, avoid motion for frequent interactions, provide alternatives, and preserve comfort. Its product films and keynote grammar demonstrate a related editorial principle: one idea per beat, clean spatial continuity, considered silence, and a transition motivated by the thing on screen rather than a transition effect.

The Animations.dev and Emil Kowalski lens raises the bar from "animated" to "feels right": duration and easing are authored decisions; entry and exit have different energy; high-frequency behavior earns less spectacle; performance and taste are inseparable. Linear, Raycast, Arc, Vercel, and Stripe demonstrate product confidence through fast comprehension, disciplined typography, exact detail, and a refusal to ornament routine states. Notion, Craft, Pitch, and Nothing show that an expressive brand can remain coherent when its visual system has limits.

Remotion's model changes the production discipline: time is a frame-indexed function, not a browser animation that happens to be recorded. Therefore every important image, transition, audio cue, and edit decision must be deterministic at any frame. GSAP and Motion are useful conceptual references for timeline composition, property-specific transitions, labels, and orchestration, but browser-run timelines and CSS animations are not the render path in a Remotion composition.

### Research sources

- [Apple Human Interface Guidelines: Motion](https://developer.apple.com/design/human-interface-guidelines/motion?changes=_3)
- [Apple accessibility: reduced-motion evaluation](https://developer.apple.com/help/app-store-connect/manage-app-accessibility/reduced-motion-evaluation-criteria)
- [animations.dev](https://animations.dev/)
- [Emil Kowalski design-engineering skill](https://github.com/emilkowalski/skills/blob/main/skills/emil-design-eng/SKILL.md)
- [Remotion documentation](https://www.remotion.dev/docs/)
- [Motion documentation](https://motion.dev/docs/animate)
- [GSAP learning resources](https://gsap.com/resources/)

References are studied for principles, never copied in shot design, cadence, wording, visual identity, music, or proprietary UI.

### Quality checklist

- [ ] A reference board names the principle observed beside each reference.
- [ ] The board contains no instruction to imitate a company's visual signature.
- [ ] Each proposed treatment has an explicit reason it is appropriate for Lokalo and this audience.

---

## 4. Creative Direction

### Philosophy

Lokalo is an operating system for hospitality teams. Its films should make complexity feel contained, not make management look like science fiction. The dramatic contrast is between fragile, distributed operational knowledge and a shared, clear working reality. We show tempo, responsibility, and relief.

### Message hierarchy

Write the hierarchy before storyboards:

1. **Human truth:** what does the operator, manager, owner, or employee need to stop carrying alone?
2. **Product action:** what does Lokalo make possible now?
3. **Proof:** what visible state proves it?
4. **Business implication:** why does this matter this shift, this week, or this venue?
5. **Brand close:** why is Lokalo the credible partner?

The first 3 seconds establish tension or category. Seconds 3-12 establish action and proof. The final third converts understanding into confidence and a single next step. These are guidelines, not a license for a rigid three-act template.

### Treatment selection

Use one primary treatment per production:

- **Operational pulse:** real hospitality detail, practical light, calm overlays, product as the organizing force.
- **Product proof:** screen-led but editorial; a feature's before, action, and after in one visual language.
- **Founder/voice thesis:** a human point of view supported by product evidence, never an empty manifesto.
- **Launch reveal:** controlled escalation from category tension to a single new capability.
- **Feature explainer:** task-first, slow enough to learn, modular enough to cut into help content.

Do not mix treatments merely to create variety. Change visual energy only when the meaning changes.

### Common mistakes

- Calling every feature "revolutionary."
- Putting five interface states on screen before any can be read.
- Opening with logo, then explaining why the viewer should care.
- Simulating a restaurant with irrelevant stock imagery.
- Treating UI as a texture rather than evidence.

---

## 5. Story, Script, and Editorial Structure

### Script format

Every line has a function tag: `[TENSION]`, `[CONTEXT]`, `[ACTION]`, `[PROOF]`, `[OBJECTION]`, `[RESULT]`, `[CTA]`, or `[SILENCE]`. If a line cannot be tagged, it is likely filler. Pair each line with its visual evidence and its audio plan before approval.

Use active, operational language: "Know who is on floor at 18:00" is stronger than "Powerful workforce visibility." Say what changes, for whom, and when. Avoid unverified superlatives, generic productivity promises, and numbers without source or scope.

### Beat sheet

For each beat record: in/out frame, audience question, visual subject, camera state, dominant read, on-screen copy, voiceover, SFX, music state, transition motivation, product source, and approval owner. The beat sheet is the contract between creative, motion, sound, and engineering.

### Editing rules

- Cut on a change in idea, direction, action, sound, or emotional temperature, not merely on a beat.
- Keep a shot until its primary read is complete; remove it immediately after it has paid off.
- Use match cuts when shape, direction, scale, or action makes the relationship meaningful.
- Use a hard cut when the new fact is stronger than continuity.
- Let a result settle. A proof shot needs reading time, not just arrival time.
- Do not cut every beat of a music track. The edit leads; music supports.

### Quality checklist

- [ ] A first-time viewer can describe the sequence of cause and effect.
- [ ] The script contains at least one intentional silence or visual hold where useful.
- [ ] Every sentence earns its duration.
- [ ] There is one unambiguous CTA, or a deliberate reason not to use one.

---

## 6. Storyboards, Animatics, and Scene Plans

### Storyboard standard

Storyboard in 16:9 first unless the primary deliverable is vertical. Every board includes frame range, estimated duration, composition diagram, subject, camera movement, on-screen copy, product state, transition in/out, and sound cue. Draw the intended negative space; it is as important as the subject.

Annotate layers as `BG`, `ENV`, `PRODUCT`, `TYPE`, `FX`, `CAMERA`, `SFX`, `MUSIC`, and `VO`. Use arrows only for real motion. Do not draw decorative arrows that imply movement which will not be made.

### Animatic standard

Build the animatic in Remotion at target fps with temporary assets, approved copy, scratch voice, and timing. It must be watchable end-to-end before detailed animation begins. Sound is introduced at animatic stage because it changes perceived duration and cut logic.

### Scene plan template

| Field | Required decision |
|---|---|
| Scene purpose | One audience understanding to create |
| Start/end state | What visibly changes |
| Hero subject | Person, product state, object, or type |
| Camera | Locked, track, push, pull, pan, tilt, or cut |
| Motion hierarchy | Primary, secondary, ambient, none |
| Audio | Lead cue, bed, silence, transition cue |
| Accessibility | Captions, contrast, reduced-motion alternative |
| Evidence | Product build / filmed source / legal approval |

### Common mistakes

- Starting detailed motion before duration and message are approved.
- Treating an animatic as a slideshow instead of an editorial test.
- Planning visual shots without sound cues.
- Designing a desktop storyboard that cannot crop to vertical.

---

## 7. Visual Language, Brand, and Composition

### Visual language

Lokalo Noir uses near-black or charcoal foundations, accurate product surfaces, restrained warm practical imagery, and mint only as a meaningful state, action, confirmation, or brand signal. White space is not empty; it assigns authority. Use texture from real material, photography, and product detail, not simulated noise used to hide weak composition.

### Brand presentation

The mark arrives after the audience has experienced the product promise. Present it with enough stillness to read. Do not spin, shatter, liquid-morph, or explode the logo. A short optical settle, a precise fade, or a reveal tied to the product's grid is sufficient.

Use approved logo files only. Preserve clear space, aspect ratio, and contrast. Never recolor a mark for novelty. Build a logo end card as a reusable composition with legal line, CTA, regional copy, and audio variants.

### Composition rules

- Design from the focal subject outward; do not place a subject into a pre-existing layout.
- Use one dominant anchor, one supporting relationship, and quiet remainder.
- Align type, UI, and camera axes deliberately. Break alignment only to express tension or an intentional change of state.
- Use foreground depth only when it clarifies scale or creates a real spatial relationship.
- Keep essential type and product UI inside title-safe and action-safe bounds for each delivery format.
- Test all typography at 25% scale. If hierarchy collapses, the shot is overfilled.

### Typography

Use the current approved Lokalo marketing type system. Define a production type scale in tokens, not ad hoc pixels: display, headline, statement, label, data, caption, legal. Limit a scene to two weights unless the product UI itself requires more. Type motion follows semantic hierarchy: the thought arrives, then the qualifier, then the evidence. Never animate every word identically.

Avoid letter spacing tricks, per-character novelty animation, long all-caps paragraphs, type that competes with product UI, and text that only becomes readable after it stops moving.

### Quality checklist

- [ ] A still frame communicates the scene's hierarchy.
- [ ] Mint only communicates approved meaning.
- [ ] No branded reference is being imitated recognizably.
- [ ] Text remains readable on target device previews.

---

## 8. Camera, Light, Color, and Material

### Camera language

The camera is an editorial point of view, not a constant source of motion. Default to locked frames. Use a push when attention or understanding narrows; pull when context expands; track with an object only when it carries the story; pan or tilt to discover adjacent evidence. A move begins and ends with intent. No perpetual drift.

For product UI, simulate camera only through a documented virtual camera transform. Preserve legibility: avoid excessive perspective, large rotations, or fly-throughs that turn an interface into an abstract object. Use 3D only when depth itself communicates value.

### Lighting

Light directs the eye and establishes truth. Hospitality footage should use motivated practical sources: daylight, kitchen warmth, bar reflection, task light. Maintain facial and product readability. Do not use a cyan/orange grade as a default. Avoid glossy, anonymous dark imagery that obscures the subject.

### Color pipeline

Define working color space, source profile, monitoring target, and export transform at kickoff. Keep the palette in shared tokens. Test dark gradients for banding, captions for contrast, and all brand color uses on SDR target displays. Color grade for product accuracy before mood. A product screen is evidence, not a gradeable prop.

### Common mistakes

- Moving the camera because a still image feels insufficiently "video-like."
- Adding contrast until black product surfaces lose structure.
- Making every scene dark, then losing the ability to create dramatic contrast.
- Applying global effects to product screenshots that compromise UI fidelity.

---

## 9. Motion Direction

### Motion hierarchy

Classify every movement:

1. **Primary:** the action the audience must understand now.
2. **Secondary:** support that explains grouping, relation, or consequence.
3. **Ambient:** nearly still environmental life; remove unless it makes the world more credible.
4. **Transition:** movement whose only job is to change scenes; it must borrow meaning from either scene.

No primary action may compete with another primary action. Secondary motion starts after the primary is recognized. Ambient motion must be slower, lower contrast, and lower amplitude than the primary.

### Timing defaults

Author in frames and derive from fps. For 30 fps, use these starting ranges, then test in context:

| Event | Frames | Notes |
|---|---:|---|
| Instant acknowledgement | 3-6 | State change, not a mini-show |
| Small UI enter/exit | 6-12 | Short travel, opacity lead |
| Text phrase reveal | 8-18 | Depends on words and reading load |
| Product panel transition | 12-20 | Must preserve orientation |
| Camera push / reveal | 18-36 | Only when meaning accrues through travel |
| Scene transition | 6-18 | Cut when a transition adds no meaning |
| Logo settle | 12-24 | Hold after motion, do not keep moving |

At 24 fps, convert by time rather than preserving frame counts. Do not use durations as universal laws: reading, distance, mass, expected input, and emotional context decide the final value.

### Easing system

Centralize named curves. Never use an unnamed default `ease` for a hero decision. Use one family per production unless contrast is explicitly designed.

- **Enter:** decisive ease-out; fast arrival, gentle settle.
- **Exit:** ease-in; leaves promptly and preserves attention for what follows.
- **On-screen reposition:** symmetrical ease-in-out, unless an object is responding to a physical cause.
- **State confirmation:** short, restrained overshoot only when it implies tactility or completion.
- **Camera:** smooth, no surprise acceleration; avoid bounce.

Springs are not a style. Use them when material response, direct manipulation, or a tactile interaction requires them. Rendered marketing films often need duration-controlled interpolation for edit precision. Clamp overshoot where a UI edge, text baseline, or logo would visibly wobble.

### Transition grammar

Choose from: cut, match cut, object wipe, product-surface wipe, focus shift, scale continuation, directional continuation, hold/fade, or reveal through a meaningful mask. Prohibit random zoom blur, whip-pan, glitch, light leak, lens flare, and morph transitions unless the actual story establishes that material language.

### Motion review questions

- What changes, and why now?
- Is the motion faster than comprehension but slower than boredom?
- Does the animation preserve the viewer's mental model?
- Would a cut be clearer?
- Does the sound reinforce the same material and direction?

---

## 10. Audio Direction and Sound System

### Philosophy

Sound is motion made physical. Every purposeful movement is evaluated for sound, including the decision that it should be silent. The soundscape establishes scale, material, direction, pace, and confidence before viewers consciously identify it. Never add a sound merely because something moved.

### Layer model

1. **Voice:** narration, interview, or spoken product truth; always intelligible.
2. **Music:** structural energy and emotional temperature, never a metronome dictating every edit.
3. **World:** room tone, kitchen, hospitality environment, air, equipment, or real ambience.
4. **UI/tactile:** taps, selection ticks, confirmations, data arrival, panel movement.
5. **Kinetic:** whooshes, impacts, risers, camera movement, logo sound, and transitions.
6. **Silence:** intentional absence that gives a fact, cut, or close authority.

### Sound taxonomy

- **Swoosh/whoosh:** directional travel or a transition with meaningful velocity. Match pitch and stereo movement to trajectory; do not use for a 2px UI shift.
- **UI tick:** a brief, low-profile acknowledgement. It must feel tactile, not like a mobile-game reward.
- **Impact:** completion, arrival, or a large edit. Use low-end sparingly and leave headroom for it.
- **Riser:** anticipation for an earned reveal. Stop before the reveal if silence creates more authority.
- **Ambient layer:** establishes place. Use real or credible room tone and avoid a continuous synthetic hum as filler.
- **Camera movement:** air, subtle shift, or mechanical texture only if the camera move represents a material point of view.
- **Logo:** short, recognizable, non-gimmicky mnemonic with a silent variant. It follows brand resolve, not a stock cinematic boom.

### Synchronization

All cue points are frames: `frame`, `durationInFrames`, `offsetFrames`, `gain`, `pan`, and `duckTarget`. Establish sync markers for first frame of visibility, maximum velocity, contact, settle, cut, voice word, and music downbeat. A sound may lead a visual by 1-3 frames for anticipation or land 1-2 frames late for mass; document deviations.

### Stereo and spatial design

Mix for stereo first, but confirm mono compatibility. Pan only when the visual establishes direction; do not make the audience chase UI sounds around headphones. Keep voice centered. Keep important low-frequency information centered. Use width for world, air, and controlled transitions. Treat spatial audio as an enhancement layer, not a requirement for comprehension.

### Mixing and mastering

Use project targets supplied by distribution and the music/VO team; do not normalize blindly. Create stems for VO, music, world, UI, and kinetic effects. Automate music ducking around speech rather than permanently lowering the entire track. Check intelligibility on studio monitors, headphones, laptop speakers, and phone speakers. Watch true peaks and codec behavior. Deliver an approved master, a textless master, M&E where needed, and stems when contracted.

### Audio checklist

- [ ] Every primary movement has an intentional sound decision: cue, quiet support, or silence.
- [ ] VO remains intelligible under all music and effects.
- [ ] The first frame of each cut has no unintended click, tail, or missing room tone.
- [ ] Stereo decisions survive mono fold-down.
- [ ] Licensed audio metadata and source files are recorded.

---

## 11. Remotion Architecture

### Principles

Remotion is the source of timeline truth. The composition owns dimensions, fps, duration, and validated input props. Scenes own visual assembly. Shared primitives own timing and behavior. Tokens own brand decisions. Audio cues own synchronization. No scene reaches into another scene's private state.

All animation derives from `useCurrentFrame()` and `useVideoConfig()`. Use `interpolate()` with explicit clamp behavior and named easing. CSS transitions, CSS keyframe animation, uncontrolled timers, random values, current time, and network-dependent render behavior are forbidden in final compositions because they are not deterministically frame-rendered.

### Recommended structure

```text
promo/
  public/
    brand/              # Approved logo, fonts, legal assets
    media/              # Licensed, versioned footage and audio
  src/
    Root.tsx            # Composition registration and schemas
    compositions/       # Top-level deliverables only
    scenes/             # Scene assemblies, no global side effects
    components/         # ProductFrame, TitleBlock, LogoEndCard, etc.
    motion/             # Enter, exit, camera, stagger, transitions
    audio/              # Cue maps, AudioBus, ducking, sound tokens
    theme/              # Colors, type, spacing, easing, durations
    data/               # Validated briefs, copy, scene configuration
    lib/                # Frame math, validation, deterministic helpers
```

### Composition contract

Each composition has a stable id, Zod schema, `defaultProps`, documented intended use, duration calculation where variable, and a preview fixture. Compositions must not depend on hidden global values. Give compositions semantic ids such as `LaunchFilm16x9`, `FeatureSchedule9x16`, and `LogoEndCard1x1`, not campaign nicknames that become misleading.

Use `calculateMetadata` only for metadata that can be resolved deterministically and safely. Avoid querying mutable production APIs at render time. Resolve remote assets before render or pin versioned URLs with a failure policy.

### Shared timing and tokens

```ts
export const timing = {
  fps: 30,
  ui: { acknowledge: 4, enter: 10, exit: 8 },
  scene: { transition: 14, settle: 18 },
} as const;

export const easing = {
  enter: Easing.bezier(0.16, 1, 0.3, 1),
  move: Easing.bezier(0.65, 0, 0.35, 1),
  exit: Easing.bezier(0.7, 0, 0.84, 0),
} as const;
```

Tokens are starting points, not a replacement for review. A scene may use a different duration only with an explanatory name and a storyboard reason.

### Motion primitives

Build small, inspectable primitives: `fade`, `slideIn`, `revealMask`, `scaleSettle`, `cameraPush`, `stagger`, `hold`, `cut`, and approved `transition` functions. Each primitive receives frame-relative inputs and returns values or a style object. It never decides a story beat. Do not create a generic `animateEverything` component.

Use `<Sequence from={...} durationInFrames={...}>` for temporal isolation. Prefer local frame calculation inside a scene or primitive. Define absolute cue markers in scene data, then use relative frames within the scene. Set `layout="none"` when a sequence must preserve inline layout. Use `<AbsoluteFill>` only where full-frame layering is intended.

### Product capture components

Product UI must be represented with clear ownership:

- `ProductFrame`: approved browser/device chrome, safe crop, and scale behavior.
- `ProductState`: a fixture or captured state whose version is recorded.
- `Cursor` / `TouchPoint`: only when an input action needs explanation; no wandering cursor.
- `FocusTreatment`: dimming, crop, or callout only after accessibility/readability review.

Never animate live application code in a final render without a locked fixture. Product changes must not silently alter a film.

---

## 12. Remotion Audio, Assets, and Performance

### Audio implementation

Store cue maps as typed data. The scene renders a shared `AudioBus`; the bus maps cue tokens to `<Audio>` elements, trims with frame offsets, applies frame-based gain envelopes, and exposes stems/mute switches for review. Use `staticFile()` for local `public/` assets. Name assets by category, source, version, and rights status.

Example cue data:

```ts
type Cue = {
  id: string;
  src: string;
  from: number;
  duration?: number;
  gain: number;
  pan?: number;
  role: "music" | "world" | "ui" | "kinetic" | "voice";
};
```

### Asset policy

Every asset has source, license, creator, expiration/restriction, approval owner, color treatment, intended formats, and checksum/version. Keep originals immutable. Derivatives state their source. Do not check large temporary exports or cache artifacts into version control. Use an asset manifest so an editor can replace media without editing shot logic.

### Rendering performance

- Pre-size images and use Remotion's `<Img>` for images.
- Use `staticFile()` for public local assets.
- Keep effects and DOM complexity proportional to resolution and shot duration.
- Pre-render expensive source media, but preserve an editable source asset.
- Avoid per-frame allocations, uncontrolled layout measurement, and large blur/filter stacks over full HD/4K frames.
- Test representative stills, then a short range render, then the final target render.
- Use deterministic seeds only where procedural variation is genuinely required; seed from stable composition/scene data.

### Render matrix

At minimum review: 16:9 1920x1080, 9:16 1080x1920, 1:1 1080x1080 when required, captions on/off, audio stems, and a still from every scene's first, peak, and last meaningful frame. Do not crop a master mechanically when a composition's focal point changes; use responsive shot rules or dedicated compositions.

---

## 13. Production Pipeline

### 1. Intake and strategy

Write a brief: objective, audience, funnel stage, single action, mandatory product truth, claim substantiation, channels, aspect ratios, duration range, budget, launch date, legal constraints, and approvals. Reject ambiguous requests before visual production.

### 2. Research and creative territory

Collect audience evidence, product source, brand constraints, and principle-based references. Create two or three distinct territories only when a decision is needed. Each territory must answer the same brief; do not present variations that change the message.

### 3. Script, beat sheet, storyboard

Approve message and timing before high-fidelity design. Mark placeholder material visibly. Product Marketing approves claims; Product approves UI truth; Creative approves direction; Sound approves early rhythm.

### 4. Animatic

Implement the complete film with temporary assets and working audio. Review pace, comprehension, copy, and cut logic. This is the lowest-cost point for structural change. Do not begin polish while the animatic has unresolved story notes.

### 5. Design and build

Build a scene at a time on shared primitives. Add asset metadata as assets arrive. Create still-frame contact sheets. Maintain a shot ledger linking frame ranges to source files and approvals.

### 6. Sound, color, and finishing

Replace scratch audio, mix, grade, caption, and produce legal/textless variants. Do not treat audio as post-production decoration; refine it as visual timing changes.

### 7. QA, approvals, master

Run automated checks, technical checks, full creative review, accessibility check, and delivery-specific review. Lock the approved source revision and render manifest. Archive source, assets, contracts, exports, and feedback.

### Revision protocol

All feedback is logged by timestamp/frame, category, severity, owner, and desired outcome. Consolidate feedback before a revision pass. A comment such as "make it more premium" is not actionable until translated into a specific hierarchy, timing, material, sound, or message problem. Do not execute contradictory notes without an approver decision.

---

## 14. Production System Specification

### Animation principles

Animate with staging, anticipation, follow-through, overlap, arcs, contrast in velocity, and deliberate holds only when they improve a viewer's ability to understand the intended action. In this system, the classic principles are editorial tools rather than a mandate to make interfaces behave like characters. Staging means the subject is readable before it moves. Anticipation may be a sound lead, focus shift, or tiny pre-move, but it is omitted when it slows a direct action. Follow-through belongs to materials and camera inertia, not to text or interface panels that should settle exactly.

### Storytelling implementation

Storytelling lives in the data model as well as the script. Define `beats`, `scenes`, and `proofs` separately. A beat expresses the audience change; a scene expresses visible assembly; a proof identifies the approved source. This prevents visual polish from replacing an actual narrative. The same story can drive a 60-second film, 15-second cut-down, or vertical feature proof by selecting an approved beat subset rather than arbitrarily speeding up the master.

### Reusable components

Components are visual building blocks with a single responsibility: `TitleBlock`, `Kicker`, `ProductFrame`, `MetricCallout`, `BrowserChrome`, `DeviceFrame`, `LogoEndCard`, `CaptionLayer`, and `LegalLine`. They accept explicit props, expose documented variants, and contain no campaign copy or absolute scene timing. A component is reusable only when it reduces repeated decisions without flattening distinct scenes into the same design.

### Reusable motion

Reusable motion consists of frame-based primitives and transition recipes, not pre-baked spectacle. Each recipe documents the intended semantic use, frame range, easing, compositing requirements, and sound recommendation. Examples: `enterFromFocus`, `exitToCut`, `continuityPush`, `surfaceWipe`, and `phraseReveal`. A recipe cannot choose its own duration based on hidden assumptions and must always allow a still/no-motion state for review.

### Reusable audio

Maintain a curated library of approved audio tokens: `ui.select.soft`, `ui.confirm.mint`, `transition.surface.short`, `impact.low.controlled`, `riser.subtle`, `world.restaurant.evening`, and `brand.logo.primary`. Tokens reference immutable source files and usage notes, rather than encouraging direct file-path reuse. Each token lists loudness, duration, material, stereo character, rights, and prohibited contexts.

### Asset management

The asset manifest is the only authority for production media. It includes asset ID, original path, derivative path, content type, dimensions/duration, source, license, expiry, checksum, color state, approved use, and reviewer. Footage, screenshots, fonts, music, sound effects, and logos all require an entry. Remove an expired or unapproved asset from active manifests before final render; do not rely on memory or an editor's private folder.

### Code architecture

Use unidirectional dependency flow: `theme` and `lib` have no campaign dependencies; `motion`, `audio`, and `components` depend only on theme/lib; `scenes` compose shared layers; `compositions` assemble scenes and validate props; `Root` registers compositions. Data/config may be imported downward, never by a generic primitive that then acquires campaign knowledge. Keep type definitions near their stable domain, keep complex frame math tested, and prohibit scene-to-scene imports.

### Project structure

One campaign receives a folder in `src/data/campaigns/<campaign-id>/` containing its brief, copy, beat map, asset manifest, and scene configuration. Shared source remains outside campaign folders. Place working exports in `out/` and keep them untracked. Use `public/brand` for current approved identity assets and `public/media` only for media that must resolve at render time. Preserve source files external to web delivery folders when their size or licensing requires it, but retain manifest references.

### Revision workflow

Create a numbered revision only after a consolidated note pass. `v01` tests the animatic; `v02` addresses structural notes; later versions isolate agreed changes. Every revision report lists changed frame ranges, notes addressed, notes deferred, and newly introduced risks. A late copy or product change triggers a regression check of timing, captions, audio sync, legal copy, and every output ratio. Do not accept direct last-minute edits that bypass the log.

### Quality checklist

- [ ] The story, proof, and scene data are separate and traceable.
- [ ] Shared components and primitives remain campaign-neutral.
- [ ] Every used asset and audio token has manifest metadata.
- [ ] Revision comments map to a frame and a final disposition.

---

## 15. Independent Review System

Every production receives independent reviews from five roles. Reviewers diagnose rather than merely approve. They must identify weaknesses, including weaknesses introduced by their own discipline's priorities.

### Creative reviews

Creative reviews happen at brief, storyboard, animatic, pre-final, and master stages. The reviewer must compare the work to the approved objective and evidence, not to personal taste or a reference's surface style. A pass is approval of the stated stage only; it is not permission to skip later technical, product, or sound review.

### Creative Director

Evaluates idea, audience truth, brand distinction, hierarchy, visual coherence, and emotional arc. Rejects reference imitation, generic spectacle, and scenes without a reason to exist.

### Motion Director

Evaluates intention, choreography, timing, easing, transition motivation, hierarchy, comfort, and frame accuracy. Rejects continuous motion, unearned bounce, incoherent velocity, and effects that obscure product truth.

### Sound Designer

Evaluates material, timing, silence, VO intelligibility, stereo logic, frequency balance, music/edit relationship, and delivery mix. Rejects stock whooshes, impact inflation, masked dialogue, and sound that contradicts the picture.

### Product Marketing Director

Evaluates target audience, claim accuracy, narrative logic, category differentiation, CTA, product truth, and conversion relevance. Rejects vague benefits, unsupported metrics, feature lists, and invented states.

### Apple Design Reviewer

Evaluates clarity, focus, visual restraint, purposeful motion, continuity, legibility, accessibility, and comfort. Rejects gratuitous movement, unnecessary waiting, peripheral distraction, illegible transitions, and style over understanding.

### Redesign trigger

If two or more reviewers independently identify the same root problem, the scene is redesigned, not patched. The owner records: root issue, discarded assumption, new hypothesis, revised storyboard, and re-review result. Do not count repeated wording as independent agreement; identify the shared underlying failure.

### Review severity

- **Blocker:** false claim, unreadable content, broken output, rights issue, accessibility failure, or story failure.
- **Major:** material hierarchy, timing, product-truth, audio, or brand issue that changes effectiveness.
- **Minor:** polish issue with no change to comprehension or credibility.
- **Observation:** optional exploration, never silently treated as a requirement.

---

## 16. Quality Assurance and Export Checklist

### Creative QA

- [ ] The opening gives a reason to watch without explaining everything.
- [ ] Product screens are current, honest, readable, and approved.
- [ ] Each shot has one dominant read and a clear exit condition.
- [ ] Copy has been proofread in every language, format, and caption track.
- [ ] Motion, edit, and sound tell the same story.
- [ ] The brand close feels earned rather than appended.

### Technical QA

- [ ] Composition id, props, dimensions, fps, and duration are confirmed.
- [ ] All assets resolve locally or are pinned and available.
- [ ] No CSS animation, wall-clock state, random unseeded behavior, or network race affects render output.
- [ ] There are no clipped type, overflow, missing fonts, broken images, dropped frames, visual banding, aliasing, or unexpected alpha.
- [ ] Captions, legal text, and safe zones are correct for each format.
- [ ] Audio begins/ends cleanly; dialogue is intelligible; mix and codec meet platform requirements.
- [ ] A final full-resolution render was watched end-to-end with sound.

### Export package

Deliver only approved variants with unambiguous names:

```text
lokalo_<campaign>_<format>_<resolution>_<fps>_<language>_<version>_<date>.<ext>
```

Include master, platform deliverables, captions/subtitles, textless variant when needed, audio stems when contracted, thumbnail/poster, source commit SHA, render command/version, and manifest. Archive the approval record with the delivery.

---

## 17. Common Failure Modes

### AI-generated production failures

- Every element fades and rises from below: replace with hierarchy-specific entrances or cuts.
- Generic cinematic whoosh at every cut: remove most cues and design the remaining ones from material and direction.
- Constant zoom/pan: lock the camera; introduce one meaningful move.
- Five fonts, weights, glows, and gradients: return to tokens and one dominant type relationship.
- Feature montage with no cause/effect: rebuild around one job and one proof.
- Per-character type animation: reserve it for rare wordplay; usually reveal phrases or cut.
- Random "premium" abstractions: use real product evidence, real environment, or honest graphic form.
- UI distorted in 3D: keep UI legible; depth must explain, not decorate.
- Animation begins at scale zero: use a subtle offset or clip/reveal unless disappearance is the story.
- Unreadable copy on a beat: reading is part of duration, not an afterthought.

### Recovery protocol

When a scene feels wrong, do not add effects. First remove ambient movement, shorten or cut the transition, reduce simultaneous information, re-check the story beat, and listen without picture. Then rebuild the primary read. A quieter scene with a stronger idea is the correct fix more often than a more elaborate scene.

---

## 18. Practical Command Guide

Use the project scripts and current Remotion CLI versions. Start Studio for composition review, render representative stills for fast visual checks, then render the approved composition. Do not claim a final render is verified until it has been watched with final audio.

```powershell
Set-Location promo
npm run studio
npx remotion still <composition-id> --frame=<frame> --output=out\check.png
npx remotion render <composition-id> out\master.mp4
```

Before changing the codebase, read the composition's source, its direct shared primitives, and the relevant asset manifest. Preserve unrelated work. Commit only a coherent, verified milestone, stage only task files, and push the approved milestone to its configured upstream.

---

## 19. Definition of Done

A production is complete only when the approved brief is satisfied; all product claims and assets are verified; five independent review roles have completed their review; duplicate root-cause feedback has triggered redesign where required; all technical, sound, accessibility, and export checks pass; final renders were watched; and source, versions, rights, approvals, and delivery files are archived.

The final question is not "does this look like a launch film?" It is: **does every second make Lokalo more understood, more credible, and more desired by the people who run hospitality operations?**

---

## Appendix A: Production Brief Template

```md
# <Campaign / Film Name>
Objective:
Audience:
Single desired action:
Core operational truth:
Product action:
Visible proof:
Claim substantiation owner:
Primary format / duration / fps:
Required variants:
Source-of-truth product build:
Approved brand assets:
Music / VO / rights:
Key message hierarchy:
Mandatory inclusions:
Forbidden claims or imagery:
Approvers and review dates:
```

## Appendix B: Scene Ledger Template

```md
| Scene | Frames | Purpose | Product / source | Visual lead | Audio lead | Transition | Owner | Status |
|---|---:|---|---|---|---|---|---|---|
| 01 | 0-89 | Establish tension | filmed venue | service pressure | room tone + sparse pulse | hard cut | CD | draft |
```

## Appendix C: Preflight Questions

1. What should the right viewer understand by frame 90?
2. What is the one action the product visibly performs?
3. Which scene would still work as a silent still image?
4. Which movement would become clearer as a cut?
5. Which sound can be removed to make the important sound stronger?
6. What would a skeptical operator call vague or unbelievable?
7. What needs redesign if two independent reviewers identify it?
