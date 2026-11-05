# Life under debt: Kuroshio society design

Status: owner approved 2026-11-04. Game text is in; test images are in review.

## The actual gap

`narrator/worlds/kuroshio.toml` says chrome is financed and that torite repo crews take it back, and it says who holds power. It says little about how ordinary people live with debt. Scenes and narration therefore have no everyday texture for the world's central idea.

This design adds that texture as world text and test images. It adds no game rules.

## Owner decisions (2026-11-03)

- Deepen life under debt first, ahead of class, culture or district looks.
- Debt is visible: chrome shows a status light.
- There must be ways to hide or fake the light.
- Debt escalates as a slow, polite squeeze, with Kuze-gumi public shaming on the debts they hold.

## Research grounding

A research pass on 2026-11-03 used fetched sources:

- **Public shaming.** Japanese sarakin collectors appeared at funerals and weddings and used loudspeakers outside homes and workplaces ([Wikipedia: Sarakin](https://en.wikipedia.org/wiki/Sarakin)).
- **Guarantors.** Guarantor companies are used by an estimated 80% of Japanese renters, and collect from the tenant after paying the landlord ([Realestate guide](https://realestateguide.jp/?p=1491), [GTN](https://www.gtn.co.jp/magazine/en_us/article206/)). These are industry sources, so treat them as description.
- **Night movers.** Yonige-ya priced their work by belongings, distance, and whether collectors were being evaded ([Wikipedia: Johatsu](https://en.wikipedia.org/wiki/Johatsu)). The same page warns that English-language media exoticise johatsu, so the world should treat vanishing as a hard choice and not as mystique.
- **Remote shut-off.** US subprime auto lenders disable ignitions remotely, and borrowers have been stranded ([CBS](https://www.cbsnews.com/amp/news/why-the-repo-man-can-remotely-shut-off-your-car-engine/)). The figures date from about 2014.
- **Blacklists, not one score.** Chinese "social credit" is several programmes, and the concrete part is a court blacklist of debt defaulters that restricts travel ([Foreign Policy](https://foreignpolicy.com/2018/11/16/chinas-orwellian-social-credit-score-isnt-real/)).
- **Fiction.** *Repo Men* stages a repossession outside a family barbecue and has customers offered an ambulance ([Wikipedia](https://en.wikipedia.org/wiki/Repo_Men)). *Kaiji* pays camp labour in scrip, so cuts are felt daily ([Wikipedia](https://en.wikipedia.org/wiki/Kaiji_(manga))).

The takeaway is that debt lands hardest in domestic, ordinary places, and that polite cruelty suits Hoshikawa. *Cyberpunk: Edgerunners* and *Cyberpunk RED* were not fetched and are not cited here.

## World design

### Status light

Every piece of financed chrome has a small light near its port: green (paid up), amber (late), red (in default).

| Way around it | Who offers it | The catch |
|---|---|---|
| Cover it with sleeves, gloves or a patch | Anyone | Looks suspicious. Shops, landlords and checkpoints may ask to see the port. |
| Fake it with a green overlay | Hanabira-chō street vendors, cheaply | Fools people, not machines. Ōgane scanners read the true status, and getting caught adds a fraud fine. |
| Spoof it so the implant reports green | Off-the-books chrome-ya such as Old Hara, costly | Passes most scanners until a Hoshikawa audit. Usually paid in favours. |
| Cut it out | Kaminari Run riders | A badge of honour on the Loop, and a target for torite anywhere else. |

### The squeeze

1. **Amber.** Soft reminders. Shops begin declining small purchases.
2. **Red.** Chrome is throttled, a blacklist blocks trains and rentals, and the guarantor gets a call.
3. **Repo.** A torite crew arrives after a final courteous notice.

Debts held by the Kuze-gumi add public shaming at the debtor's workplace or family events.

### Guarantors

Most chrome needs a co-signer, who inherits the debt if the holder vanishes. Friends and relatives can therefore end up hunting each other.

### Street trades

- **Night movers** get people out before dawn, priced by distance, belongings and how hard they are being hunted.
- **Light fakers** sell overlays and spoofs.
- **Debt brokers** buy and sell debts. Jun Arakawa's work fits alongside this.
- **The Lantern Guild** already holds the data of the dead, including those who die owing.

### Manners

It is rude to mention someone's light, and asking to see it is an insult unless you are a shop, a landlord or the police. People quietly leave a gap around amber. Workers may be paid partly in company credit.

## Changes to the game text

Edits go in `narrator/worlds/kuroshio.toml` and follow its existing rules: cards are standalone, at most 400 characters, with unique names and aliases.

- A short addition to the primer covering the status light and the squeeze. Measure the primer against its size budget from the world bible spec, about 250-400 tokens.
- Up to three glossary terms, such as the night movers and the status light. Exact words are chosen in the implementation plan.
- One or two faction or trade cards for night movers and light fakers.
- A live narrator check, since a mocked suite is not sufficient: a short session in which the narrator uses the new terms and stays in tone.

No payment system, debt tracking or new engine rules. That would be its own design.

## Images

Six small test scenes in the approved medium dark look, generated after the location sheets are redone. All characters are adults, with no gore or nudity.

1. A commuter train where passengers leave a gap around one amber light.
2. A shop clerk politely declining a small purchase.
3. A removal van loading at 3 a.m., with every neighbour's lights off.
4. A clinic with three queues by payment tier.
5. A polite torite crew at a family dinner, bowing as they hand over the notice.
6. A street vendor selling green overlays in Hanabira-chō.

The owner reviews these before more are made.

## Cast

Only characters with chrome show a light, and only where it would really be visible. Try the look on 2-3 characters for owner review before changing other sheets. Approved designs stay as they are until then.

## Out of scope

- Class and geography, culture and belief, and other society topics. Each can be its own brainstorm.
- The replacement for Brother Tōru, handled as a separate design pick.
- Payment mechanics in the engine.
