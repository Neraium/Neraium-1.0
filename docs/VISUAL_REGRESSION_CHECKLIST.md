# Visual Regression Checklist

## Scope
- Frontend shell branding and interaction polish.
- Health orb behavior for `stable`, `drift`, and `separation`.
- Desktop and mobile breakpoints.

## Desktop checks
1. Launch app and verify top brand shows `Neraium` wordmark without the top `N` badge.
2. Confirm page title hierarchy: main title is clearly dominant over section titles and body copy.
3. Hover and click primary/secondary buttons and workspace nav items:
- Hover should lift subtly with soft glow.
- Active press should return to baseline position.
- Keyboard focus should show visible focus ring.
4. Validate section reveal timing:
- Panels should fade/slide in with subtle stagger.
- Motion should feel present but not distracting.

## Orb checks by state
1. `stable`:
- Minimal motion and restrained glow.
- Orb remains coherent and calm.
2. `drift`:
- Cinematic movement with richer yellow/amber bloom.
- Structure looks stressed but mostly connected.
3. `separation`:
- Energetic motion and stronger crimson glow.
- Fracture lines visible.
- Node clusters detach outward.
- Broken links flicker and snap off briefly before returning.

## Mobile checks
1. Verify top status bar brand still reads clearly on small screens.
2. Confirm orb scales correctly and motion remains legible.
3. Ensure buttons remain tappable and hover/focus styles do not break layout.
4. Check no horizontal overflow in workspace shell and cards.

## Accessibility checks
1. Enable `prefers-reduced-motion` and verify:
- Orb motion is disabled/reduced as intended.
- Section reveal animation is disabled.
2. Confirm contrast remains readable in all three orb states.

## Build gate
1. Run `npm run build` in `frontend`.
2. No build errors or warnings that block deploy.
