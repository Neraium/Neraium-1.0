# Accessibility manual verification

This checklist covers WCAG 2.2 AA behavior that automated tests cannot reliably determine. Run it before a production release that materially changes navigation, dialogs, upload, findings, charts, or status presentation.

## Assistive technology

Test the command center, Data Sources, upload progress, completed results, issue review, and settings dialog with:

- NVDA with current Chrome on Windows.
- VoiceOver with current Safari on macOS when a Mac is available.
- Windows High Contrast mode.

Confirm that headings and landmarks provide a useful page outline, control names match their visible labels, status changes are announced once without excessive repetition, decorative orb and status graphics do not add noise, and chart summaries communicate the same operational meaning as the visual.

## Keyboard-only workflows

Without using a pointer:

1. Use **Skip to main content** and confirm focus moves to the main workspace.
2. Navigate every primary and mobile navigation item and confirm focus remains visible.
3. Open the settings dialog, cycle forward and backward through every control, press Escape, and confirm focus returns to the trigger.
4. Select telemetry files through the visible **Analyze Historical Data** or **Choose File** control, submit analysis, monitor progress, retry a failure, and open completed results.
5. Navigate result tabs with Arrow keys, Home, and End; confirm the active panel and focus move together.
6. Open disclosures with Enter and Space, review an issue, enter feedback, and save it.
7. Activate investigation shortcuts and confirm focus moves to the requested evidence section.

Confirm there are no keyboard traps other than intentional dialog containment, and that all critical actions remain available at each responsive breakpoint.

## Visual and reflow checks

At browser zoom levels 100%, 200%, and 400%, and at 320 CSS pixels wide:

- Confirm no information or controls are clipped, overlap, or require two-dimensional page scrolling.
- Confirm sticky navigation and dialogs do not obscure the focused control.
- Confirm focus indicators remain visible against every surface and are not clipped.
- Confirm text can be resized without hiding status or validation messages.
- Check normal, hover, focus, selected, disabled, error, warning, and success states for text and non-text contrast.
- Confirm severity and status always include text or another non-color cue.

Automated axe checks catch many contrast failures but cannot validate text over animated gradients, composited orb visuals, browser/OS forced colors, or every transient state. Inspect those states with browser developer contrast tools and Windows High Contrast mode.

## Motion, charts, and announcements

With **Reduce motion** enabled at the operating-system level, confirm ambient orb, loading, timeline, and transition animations stop or become effectively instantaneous; smooth-scroll shortcuts must use immediate movement.

For each chart or graphical status view, confirm the accessible name is meaningful and the adjacent text or list exposes the same decision-relevant values. Hover-only titles must not contain unique information.

Throttle the network and confirm loading, upload progress, success, validation failure, retry, and results-navigation messages are announced in a logical order. Verify assertive alerts are reserved for failures requiring immediate attention.

## Known manual risk areas

- Exact pronunciation and verbosity vary between NVDA, VoiceOver, and browser combinations.
- Native file-picker and notification-permission dialogs are controlled by the operating system and require platform-specific verification.
- Real production data can create longer labels, tables, and warnings than fixtures; test representative worst-case content.
- Color contrast over animated or translucent layers requires visual sampling in rendered production states.
