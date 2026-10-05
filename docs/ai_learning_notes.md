# AI + Learning Notes

Tool used: Claude, for planning, code and debugging. Everything below happened while building and testing this project.

## Example 1: Choosing what to build
- **What I asked:** Read the challenge brief and the JD, and build the whole project.
- **What AI suggested:** Not a landing page (the brief warns everyone will build one). It suggested a referral engine instead: ₹2,000 can't buy 500 students through ads, so students have to bring each other. It built registration, personal invite links, WhatsApp sharing, a reward ladder, a college leaderboard and a growth dashboard.
- **What I changed:** I kept the idea but tested every flow myself before trusting it. I registered myself, opened my invite link in incognito and registered a teammate through it. My page then showed "1 friend joined through you" and unlocked reward 1. Only after that did I treat the asset as done.

## Example 2: A greeting that broke on my own name
- **What I asked:** Nothing. I found this while testing.
- **What AI built:** The success page greeted people by the first word of their name.
- **What I changed:** My name is "Medaram Vishnu Vardhan", and the page said "Seat reserved, Medaram", which is my surname. In Telugu and many South Indian names the surname comes first, so most of our target students would see the same problem. I had the greeting and the "X invited you" banner changed to use the full name.

## Example 3: The page promised something the app didn't do
- **What I asked:** "Does it actually send to the mailbox?"
- **What AI said:** No. The page said "the joining link comes to your WhatsApp and email", but the app only sends each registration to an n8n webhook. No message goes out until an n8n workflow is connected.
- **What I changed:** I didn't want the page to promise something false to a real student. I rewrote both lines: the form now says the invite link comes right after registering, and the success page says to save the page.

## Something AI suggested that I rejected, and why
AI recommended connecting n8n now to send welcome emails, about 20 minutes of work. I said no for this round. The 48-hour window had four required deliverables, and the email wasn't one of them. Also, n8n running on my laptop can't receive data from the deployed site on Render, so it would have worked only in a local demo. The webhook is already built, so this is first on my "next 24 hours" list.

## Smaller fixes from testing
- On my 14-inch laptop the page looked oversized at 100% zoom, and the branch dropdown cut off "AI/ML / Data Science". I tightened the spacing and shortened the label to "AI/ML / DS". The large size itself was Windows display scaling at 150%, not the page.
- I registered again with the same number written as +91..., to check duplicate handling. The app recognised me and sent me back to my existing page instead of counting me twice.
- With the demo data, the counter said "513 of 500 seats". A real student would think the workshop was full and leave. The 500 is our internal goal, not a seat limit, so the counter now shows a 1,000-seat live webinar cap, with a waitlist message if it ever fills.
- My college was typed as "Amrita vishwa vidyapeetham , ettimadai" and showed with a stray space before the comma. College names are now cleaned to one spelling (and acronyms like SRM, KL, VIT stay upper-case), so the college leaderboard doesn't split one college into several rows.

## What changed from my first idea to the final solution
My first instinct was the obvious one: a landing page plus some ads. The budget made that impossible. At an assumed ₹20–30 per lead, ₹2,000 buys roughly 70–100 registrations. So the asset had to create reach, not just collect it, which is how I got to the referral loop. Then I realised a plan is only believable if it can be measured, so I added the dashboard: pacing against 500, conversion by channel, K-factor. Testing changed things a third time: the name greeting, the honest page text and the layout fixes.

## With another 24 hours
1. Connect n8n (on n8n Cloud) for the welcome email and the T-24h and T-1h reminders, because registered isn't the same as attended.
2. A daily WhatsApp digest to each ambassador: "your college is #4, 6 behind #3", pulled from the dashboard.
3. Referral fraud checks: the same device, or disposable emails, farming rewards.
4. An A/B test of two WhatsApp share messages, with the winner shown on the dashboard.
5. Attendance tracking, so success is measured by who shows up, not only who registers.
