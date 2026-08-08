# Open questions

What I would have asked before anyone acted on this output, and the assumption I made in
the meantime so the work was not blocked waiting for an answer.

Every one of these is live in the code today. If an answer changes, the change is one edit
to [`src/config.py`](src/config.py) and the tests will tell you what moved.

---

### 1. Is the supplier lead time two months?

**Why it matters:** it drives every reorder quantity and every order-by date in the
briefing. It is the single assumption with the widest blast radius.

**What the data says:** nothing. Lead time is not a column. I inferred it from
`Order_Arrival_Months`, where confirmed shipments land one to two months out, and assumed
**two months** as the time between placing an order and receiving it — three for MGO 1700+
100g, since the brief says it has longer lead times.

**Why this needs confirming:** if the real lead time is three months, several SKUs that the
briefing calls "act now" are already unrecoverable, and the recommendation changes from
"order this week" to "manage the stockout and tell the retail accounts". The ranking would
survive; the urgency would not.

---

### 2. Can the inbound MGO 100+ 250g order be deferred, or is it paid and on the water?

**Why it matters:** this is the briefing's headline recommendation, and it is the one
recommendation I cannot fully stand behind without an answer.

**The situation:** the SKU has the weakest growth in the range and roughly three times its
target cover, with 2,000 more units arriving. The brief's advice is to hold that shipment
and redirect the capital.

**Why this needs confirming:** "hold the order" is only advice if holding is possible. If
the goods are paid for and in transit, the real decision is a demand-side one — promotion,
bundling, channel push — and the briefing should be recommending that instead. Same
finding, completely different action.

---

### 3. Does the phase-out of Propolis Tincture have a firm date?

**Why it matters:** the brief says Q2 2026 and says not to reorder above 30 days of cover.
Both are followed. But the SKU runs dry around mid-May, which is *inside* Q2, not after it.

**What that implies:** a gap of several weeks with no product before the planned end of
life. That is a customer-communications decision and a retail-accounts conversation, not an
inventory one — and somebody needs to own it. The briefing flags the date; it cannot make
the call.

---

### 4. Is the target cover measured on arrival, or does it include the lead time?

**Why it matters:** it changes every reorder quantity by roughly a third.

**What I assumed:** that the target is the buffer you want *when the stock lands*, so a
reorder covers the lead time **plus** the target. Ordering only `target × demand` would put
the SKU at zero cover on the day the shipment arrives, which is not what a buffer means.

**Why this needs confirming:** it is a reasonable reading, not the only one. If supply
chain defines the target as inclusive of transit, the quantities in the briefing are
overstated.

---

### 5. Is March representative, or is there seasonality I cannot see?

**Why it matters:** every projection here extrapolates a four-month trend.

**What I cannot know from the data:** four months is not enough to separate growth from
season. Manuka honey plausibly has a Northern Hemisphere winter skew, and December to March
covers exactly one side of that. If Q2 is structurally softer in the US, the projected
demand driving the revenue ranking is too high across the board.

**What I would want:** the same table for the previous year. It would not change the
ranking much — the relative order is fairly robust — but it would change how confidently
anyone should read the absolute figures.

---

### 6. Should retail be in this picture?

**Why it matters:** the brief says Manukora sells through Shopify, Amazon **and retail**,
but the dataset has two channels.

**What I assumed:** that pooled inventory means retail draws on the same stock and is
either out of scope for this exercise or already inside these numbers.

**Why this needs confirming:** if retail is a third, unmeasured draw on the same pooled
position, every cover figure in this briefing is optimistic — and the SKUs already below
buffer are worse off than reported.
