# MGP AI Tour Assistant - Comprehensive UI/UX Test Guide

**Test Date:** February 22, 2026  
**Application URL:** http://localhost:8080  
**Tester:** _________________  
**Browser:** _________________  
**Screen Resolution:** _________________

---

## Test Execution Instructions

For each test step:
1. ✅ Mark as PASS if working correctly
2. ❌ Mark as FAIL if there's an issue
3. Take a screenshot and note the filename
4. Document any visual issues, bugs, or inconsistencies in the "Observations" column

---

## PHASE 1: Initial Page Load

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 1.1 | Navigate to http://localhost:8080 | Page loads successfully | ☐ | `01_initial_load.png` | |
| 1.2 | Check demo page text | "Сеть Магазинов Горящих Путевок" header visible and readable | ☐ | | |
| 1.3 | Check launcher button | Red circular button visible in bottom-right corner | ☐ | | |
| 1.4 | Check launcher icon | Chat icon (message bubble) visible inside button | ☐ | | |
| 1.5 | Check launcher animation | Button has subtle pulse/animation (if implemented) | ☐ | | |
| 1.6 | Check page layout | Demo text centered, no layout issues | ☐ | | |
| 1.7 | Check fonts | Inter font loaded correctly (not system fallback) | ☐ | | |

**Visual Quality Checklist:**
- [ ] Text is crisp and readable
- [ ] Button has proper shadow/depth
- [ ] Colors match brand (red button)
- [ ] No console errors in DevTools
- [ ] Page loads in < 2 seconds

---

## PHASE 2: Open Chat Widget

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 2.1 | Click red launcher button | Chat widget opens smoothly from bottom-right | ☐ | `02_chat_opened.png` | |
| 2.2 | Check opening animation | Smooth slide-up or fade-in animation | ☐ | | |
| 2.3 | Check widget size | Widget is appropriately sized (not too large/small) | ☐ | | |
| 2.4 | Check header | Header shows "Сеть Магазинов Горящих Путевок" | ☐ | | |
| 2.5 | Check header logo | Globe icon visible in header | ☐ | | |
| 2.6 | Check close button | X button visible in top-right of header | ☐ | | |
| 2.7 | Check welcome message | Welcome message visible with emoji and bullet points | ☐ | | |
| 2.8 | Check welcome message content | Contains: 🔍 Подобрать тур, 🔥 Найти горящие предложения, ❓ Ответить на вопросы | ☐ | | |
| 2.9 | Check bot avatar | Globe icon visible next to welcome message | ☐ | | |
| 2.10 | Check input field | Input field visible with placeholder "Введите ваш запрос..." | ☐ | | |
| 2.11 | Check send button | Send button (paper plane icon) visible and enabled | ☐ | | |
| 2.12 | Check footer | "Powered by MGP AI" text visible at bottom | ☐ | | |
| 2.13 | Check launcher button state | Launcher button now shows X icon (close state) | ☐ | | |

**Visual Quality Checklist:**
- [ ] Header has proper background color and contrast
- [ ] Welcome message is properly formatted with line breaks
- [ ] Emojis render correctly
- [ ] Input field has proper border and focus state
- [ ] Send button has hover effect
- [ ] Scrollbar is styled (if visible)
- [ ] Widget shadow/elevation looks professional
- [ ] No text overflow or clipping

---

## PHASE 3: Send Tour Search Request (Turkey)

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 3.1 | Click in input field | Input field receives focus, cursor visible | ☐ | | |
| 3.2 | Type: "Хочу тур в Турцию на двоих на 7 ночей, все включено, бюджет до 200000 рублей, вылет из Москвы в марте" | Text appears in input field without lag | ☐ | | |
| 3.3 | Check send button state | Send button remains enabled | ☐ | | |
| 3.4 | Click send button (or press Enter) | Message is sent | ☐ | `03_message_sent.png` | |
| 3.5 | Check user message display | User message appears in chat with user avatar | ☐ | | |
| 3.6 | Check user message styling | Message has proper background, padding, alignment (right side) | ☐ | | |
| 3.7 | Check typing indicator | Typing indicator appears (3 animated dots) | ☐ | `04_typing_indicator.png` | |
| 3.8 | Check bot avatar during typing | Bot avatar visible next to typing indicator | ☐ | | |
| 3.9 | Wait 30-60 seconds | Response loads (API processes search) | ☐ | | |
| 3.10 | Check bot text response | Bot responds with text message about search | ☐ | `05_bot_response_text.png` | |
| 3.11 | Check bot message styling | Message has proper background, padding, alignment (left side) | ☐ | | |
| 3.12 | Wait for tour cards | Tour cards appear below text response | ☐ | `06_tour_cards_loaded.png` | |

**Visual Quality Checklist:**
- [ ] User message is right-aligned
- [ ] Bot message is left-aligned
- [ ] Avatars are properly sized and aligned
- [ ] Typing animation is smooth
- [ ] No layout shift when messages appear
- [ ] Auto-scroll works correctly
- [ ] Text wraps properly (no overflow)

---

## PHASE 4: Tour Cards Visual Inspection

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 4.1 | Check cards container | Cards appear in horizontal carousel layout | ☐ | `07_cards_overview.png` | |
| 4.2 | Check number of visible cards | 3 cards visible initially (or less if fewer results) | ☐ | | |
| 4.3 | Check card images | Hotel images load successfully | ☐ | | |
| 4.4 | Check image fallback | If image fails, placeholder appears (🏨 emoji or fallback image) | ☐ | | |
| 4.5 | Check star rating badge | Star rating (★★★★★) visible on image | ☐ | | |
| 4.6 | Check hotel rating | Numeric rating (e.g., 8.5) visible if available | ☐ | | |
| 4.7 | Check hotel name | Hotel name clearly visible and not truncated | ☐ | | |
| 4.8 | Check location | Country and resort visible with 📍 icon | ☐ | | |
| 4.9 | Check flight info | "✈️ Перелёт: Включён (Москва)" visible | ☐ | | |
| 4.10 | Check dates | Dates in format DD.MM – DD.MM | ☐ | | |
| 4.11 | Check nights | "X ночей" with correct Russian plural form | ☐ | | |
| 4.12 | Check meal type | Meal description (e.g., "Всё включено") visible | ☐ | | |
| 4.13 | Check room type | Room type visible with proper styling | ☐ | | |
| 4.14 | Check price | Price formatted with spaces (e.g., "150 000 ₽") | ☐ | | |
| 4.15 | Check price label | "за тур" label visible below price | ☐ | | |
| 4.16 | Check price per person | "X ₽ за человека" visible if available | ☐ | | |
| 4.17 | Check "Оформить тур" button | Primary button visible with ✈️ emoji | ☐ | | |
| 4.18 | Check "Забронировать через чат" button | Secondary button visible | ☐ | | |
| 4.19 | Check card spacing | Proper spacing between cards (12px gap) | ☐ | | |
| 4.20 | Check card shadows | Cards have subtle shadow for depth | ☐ | | |

**Visual Quality Checklist:**
- [ ] All images are same height (consistent)
- [ ] Text is readable (good contrast)
- [ ] Icons are properly aligned
- [ ] Price is prominent and easy to read
- [ ] Buttons are properly styled
- [ ] No text overflow anywhere
- [ ] Cards have rounded corners
- [ ] Hover states work on buttons
- [ ] Card layout is balanced

---

## PHASE 5: Tour Cards Navigation

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 5.1 | Check navigation arrows | Left (‹) and right (›) arrows visible above cards | ☐ | | |
| 5.2 | Check navigation hint | "← листайте →" hint visible | ☐ | | |
| 5.3 | Check tour count | "Найдено X туров" text visible | ☐ | | |
| 5.4 | Hover over right arrow (›) | Arrow changes appearance on hover | ☐ | | |
| 5.5 | Click right arrow (›) | Cards scroll smoothly to the right | ☐ | `08_cards_scrolled_right.png` | |
| 5.6 | Check scroll behavior | Smooth scroll animation (not instant jump) | ☐ | | |
| 5.7 | Hover over left arrow (‹) | Arrow changes appearance on hover | ☐ | | |
| 5.8 | Click left arrow (‹) | Cards scroll smoothly to the left | ☐ | `09_cards_scrolled_left.png` | |
| 5.9 | Try touch/swipe (mobile) | Cards can be swiped horizontally | ☐ | | |
| 5.10 | Try mouse drag | Cards can be dragged with mouse | ☐ | | |

**Visual Quality Checklist:**
- [ ] Arrows are clearly visible
- [ ] Arrows have good hover states
- [ ] Scroll is smooth (not janky)
- [ ] Cards don't overlap during scroll
- [ ] Scroll stops at correct position
- [ ] No horizontal scrollbar visible

---

## PHASE 6: "Show More" Button

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 6.1 | Look for "Показать ещё" button | Button visible below cards if more than 3 tours | ☐ | | |
| 6.2 | Check button text | Shows correct count (e.g., "Показать ещё 7 туров") | ☐ | | |
| 6.3 | Check button icon | Down arrow (↓) icon visible | ☐ | | |
| 6.4 | Hover over button | Button changes appearance on hover | ☐ | | |
| 6.5 | Click "Показать ещё" | Button triggers action | ☐ | `10_show_more_clicked.png` | |
| 6.6 | Check new cards | Additional cards appear in carousel | ☐ | | |
| 6.7 | Check button state | Button disappears after showing all cards | ☐ | | |
| 6.8 | Check scroll behavior | Page auto-scrolls to show new cards | ☐ | | |

**Visual Quality Checklist:**
- [ ] Button is centered
- [ ] Button has proper styling
- [ ] New cards render correctly
- [ ] No duplicate cards appear
- [ ] Layout doesn't break

---

## PHASE 7: Button Interactions

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 7.1 | Hover over "Оформить тур" button | Button shows hover effect | ☐ | | |
| 7.2 | Click "Оформить тур" button | Opens hotel link in new tab | ☐ | | |
| 7.3 | Check new tab | Hotel booking page opens (or placeholder) | ☐ | | |
| 7.4 | Return to chat tab | Chat is still open and functional | ☐ | | |
| 7.5 | Hover over "Забронировать через чат" | Button shows hover effect | ☐ | | |
| 7.6 | Click "Забронировать через чат" | Sends booking message to chat | ☐ | `11_booking_message_sent.png` | |
| 7.7 | Check booking message | Message appears: "Хочу забронировать тур в [Hotel Name]" | ☐ | | |
| 7.8 | Check bot response | Bot responds to booking request | ☐ | | |

**Visual Quality Checklist:**
- [ ] Hover effects are smooth
- [ ] Buttons don't shift layout on hover
- [ ] Click feedback is immediate
- [ ] Links open in new tab correctly
- [ ] Booking message is properly formatted

---

## PHASE 8: Second Search Request (Egypt)

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 8.1 | Click in input field | Input field receives focus | ☐ | | |
| 8.2 | Type: "А покажите такие же варианты но в Египет" | Text appears in input field | ☐ | | |
| 8.3 | Send message | Message is sent | ☐ | `12_egypt_request_sent.png` | |
| 8.4 | Check typing indicator | Typing indicator appears | ☐ | | |
| 8.5 | Wait 30-60 seconds | Response loads | ☐ | | |
| 8.6 | Check bot response | Bot responds with text about Egypt tours | ☐ | `13_egypt_response.png` | |
| 8.7 | Check new tour cards | New cards appear with Egypt tours | ☐ | `14_egypt_cards.png` | |
| 8.8 | Check card content | Cards show Egyptian hotels/resorts | ☐ | | |
| 8.9 | Check location field | Location shows "Египет, [Resort]" | ☐ | | |
| 8.10 | Check images | Images are different from Turkey cards | ☐ | | |
| 8.11 | Scroll up in chat | Previous Turkey cards still visible | ☐ | | |
| 8.12 | Check chat history | All messages preserved in order | ☐ | | |

**Visual Quality Checklist:**
- [ ] New cards render correctly
- [ ] No overlap with previous cards
- [ ] Chat maintains scroll position appropriately
- [ ] All previous content is intact
- [ ] No performance issues with multiple card sets

---

## PHASE 9: Close and Reopen Chat

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 9.1 | Hover over X button in header | Button shows hover effect | ☐ | | |
| 9.2 | Click X button | Chat widget closes smoothly | ☐ | `15_chat_closed.png` | |
| 9.3 | Check closing animation | Smooth slide-down or fade-out animation | ☐ | | |
| 9.4 | Check launcher button | Launcher button visible again with chat icon | ☐ | | |
| 9.5 | Check demo page | Demo page still visible and intact | ☐ | | |
| 9.6 | Click launcher button again | Chat widget reopens | ☐ | `16_chat_reopened.png` | |
| 9.7 | Check conversation persistence | All previous messages still visible | ☐ | | |
| 9.8 | Check tour cards | All tour cards still rendered correctly | ☐ | | |
| 9.9 | Check scroll position | Chat scrolled to bottom (latest message) | ☐ | | |
| 9.10 | Check input field | Input field is empty and ready for new message | ☐ | | |

**Visual Quality Checklist:**
- [ ] Animations are smooth
- [ ] No content is lost
- [ ] State is preserved
- [ ] No visual glitches during close/open
- [ ] Performance is good

---

## PHASE 10: Edge Cases and Stress Tests

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 10.1 | Send very long message (500+ chars) | Message wraps properly, no overflow | ☐ | `17_long_message.png` | |
| 10.2 | Send message with special characters | Characters display correctly | ☐ | | |
| 10.3 | Send message with emojis | Emojis render correctly | ☐ | | |
| 10.4 | Send empty message | Nothing happens or error shown | ☐ | | |
| 10.5 | Click send button rapidly | No duplicate messages sent | ☐ | | |
| 10.6 | Resize browser window | Widget remains responsive | ☐ | `18_responsive.png` | |
| 10.7 | Test at 1920x1080 | Layout looks good | ☐ | | |
| 10.8 | Test at 1366x768 | Layout looks good | ☐ | | |
| 10.9 | Test at 768px width (tablet) | Widget adapts to smaller screen | ☐ | | |
| 10.10 | Test at 375px width (mobile) | Widget is full-screen or properly sized | ☐ | `19_mobile.png` | |
| 10.11 | Press Escape key | Chat closes | ☐ | | |
| 10.12 | Tab through elements | Focus order is logical | ☐ | | |
| 10.13 | Check keyboard navigation | All interactive elements accessible | ☐ | | |

---

## PHASE 11: Browser DevTools Inspection

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 11.1 | Open DevTools Console | No JavaScript errors | ☐ | `20_console.png` | |
| 11.2 | Check Network tab | All resources load successfully (200 status) | ☐ | | |
| 11.3 | Check API requests | Chat API calls return 200 status | ☐ | | |
| 11.4 | Check image loading | All images return 200 or fallback works | ☐ | | |
| 11.5 | Check CSS loading | styles.css loads successfully | ☐ | | |
| 11.6 | Check font loading | Inter font loads from Google Fonts | ☐ | | |
| 11.7 | Check Performance | Page load time < 3 seconds | ☐ | | |
| 11.8 | Check Memory | No memory leaks after multiple interactions | ☐ | | |

---

## PHASE 12: Accessibility Check

| Step | Action | Expected Result | Status | Screenshot | Observations |
|------|--------|----------------|--------|------------|--------------|
| 12.1 | Check color contrast | Text has sufficient contrast (WCAG AA) | ☐ | | |
| 12.2 | Check aria labels | Buttons have proper aria-label attributes | ☐ | | |
| 12.3 | Check focus indicators | Focused elements have visible outline | ☐ | | |
| 12.4 | Check alt text | Images have descriptive alt text | ☐ | | |
| 12.5 | Test with screen reader | Content is readable by screen reader | ☐ | | |
| 12.6 | Check heading hierarchy | Proper heading structure (if any) | ☐ | | |

---

## ISSUES FOUND

### Critical Issues (Blocks core functionality)
| # | Description | Screenshot | Steps to Reproduce | Expected | Actual |
|---|-------------|------------|-------------------|----------|--------|
| C1 | | | | | |
| C2 | | | | | |

### Major Issues (Significant UX problems)
| # | Description | Screenshot | Steps to Reproduce | Expected | Actual |
|---|-------------|------------|-------------------|----------|--------|
| M1 | | | | | |
| M2 | | | | | |

### Minor Issues (Small problems, workarounds exist)
| # | Description | Screenshot | Steps to Reproduce | Expected | Actual |
|---|-------------|------------|-------------------|----------|--------|
| m1 | | | | | |
| m2 | | | | | |

### Cosmetic Issues (Visual polish)
| # | Description | Screenshot | Steps to Reproduce | Expected | Actual |
|---|-------------|------------|-------------------|----------|--------|
| c1 | | | | | |
| c2 | | | | | |

---

## OVERALL ASSESSMENT

### Functionality Score: ___/10
### Visual Design Score: ___/10
### User Experience Score: ___/10
### Performance Score: ___/10
### Accessibility Score: ___/10

### Overall Score: ___/10

---

## RECOMMENDATIONS

### Must Fix (Before Production)
1. 
2. 
3. 

### Should Fix (High Priority)
1. 
2. 
3. 

### Nice to Have (Future Improvements)
1. 
2. 
3. 

---

## TESTER NOTES

[Add any additional observations, comments, or suggestions here]

---

**Test Completed:** _______________  
**Total Time:** _______________  
**Tester Signature:** _______________
