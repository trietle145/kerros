# Edit wars and vandalism on Wikipedia: the real issues, and what a MariaDB tool could add

Researched 2026-11-13 for the Junction MariaDB challenge (Finnish Wikipedia, history of Finland; 862,076 versions of 19,742 articles).

**How to read this.** Every claim links to the source it was read from. **(unverified)** means the page could not be loaded. wikipedia.org and meta.wikimedia.org did not load in any form (page, `?action=raw`, API, REST), so no English or Finnish Wikipedia policy page was read first-hand.

## TL;DR

**Findings**

1. **Most reverts are cleanup, not disputes, and the standard research fix is simple.** Count only *mutual* reverts (A undoes B and B undoes A) and weight each by the less experienced editor's edit count. This is the controversy measure M ([Sumi et al. 2011](https://arxiv.org/pdf/1107.3689), [Yasseri et al. 2012](https://arxiv.org/pdf/1202.3643)). It is a few SQL joins over the dataset's columns.
2. **Nobody has published this for Finnish.** The best-known multilingual study covers 10 languages and Finnish is not one of them ([Yasseri et al. 2014](https://arxiv.org/pdf/1305.5566)). We found no study or press report of edit wars on Finnish history articles. A ranked list of contested Finnish history articles would be new.
3. **sha1 revert detection has known blind spots.** It misses partial reverts and "revert plus a change" ([Research:Revert, 2021 archive copy](https://webcf.waybackmachine.org/web/20210818173454/https://meta.wikimedia.org/wiki/Research:Revert)). Passage-level tracking fixes this, and is where SVT fits best.
4. **Readers get no usable signal that a passage is contested.** Existing banners are written for editors, and about 48.5% of 1,491 test readers did not notice a notice at all ([Kuznetsov et al. 2022](https://par.nsf.gov/servlets/purl/10358961)).
5. **"Anonymous" changed meaning in 2025.** Temporary accounts replaced IP addresses ([mediawiki.org](https://www.mediawiki.org/wiki/Trust_and_Safety_Product/Temporary_Accounts)), which breaks the series for anonymous editors.

**Three most promising features**

- **Contested-passage heatmap, with "what is this fight about".** Paragraph lifetimes in a system-versioned table; vector search groups the reverted passages by meaning (idea 1 and 2).
- **Dispute score and slow edit wars across all 19,742 articles.** M per article and year, plus disputes that recur over years below the 3-per-month threshold (idea 3 and 4).
- **Vandalism survival time and a reader stability view.** How long later-reverted text stayed up, and which paragraphs of today's article have been stable for years (idea 5 and 6).

## 1. What an edit war is, and how Wikipedia handles it

- **Definition.** Editors repeatedly override each other's changes instead of settling it in discussion. English Wikipedia's three-revert rule says no user should revert the same page more than three times in 24 hours ([Kittur et al. 2007](https://www.gwern.net/doc/wikipedia/2007-kittur.pdf), quoting the rule). **(unverified)** from the policy page itself ([WP:EW](https://en.wikipedia.org/wiki/Wikipedia:Edit_warring)): that 3RR is "not an entitlement", so slower warring is still sanctionable; that reverting obvious vandalism is exempt; and that some topics have a one-revert rule.
- **Effect of the rule.** 3RR immediately reduced double reverts ([Kittur et al. 2007](https://www.gwern.net/doc/wikipedia/2007-kittur.pdf), citing Buriol et al.).
- **Page protection.** Admins can restrict who may edit. English Wikipedia, 2008–2015: 355,532 protection spells on 125,951 pages, median length 14 days, and 96% of ever-protected pages protected more than once. Protected articles were 0.37% of viewed articles but got 14% of views ([Hill & Shaw 2015](https://opensym.cs.fau.de/os2015/proceedings-files/p403-hill.pdf)).
- **Stronger tools for contested topics.** The main Russia-Ukraine war article was "extended-confirmed" protected (500+ edits and 30 days) within 12 hours of creation ([Kurek et al. 2024](https://arxiv.org/html/2409.02304v1)).
- **Dispute resolution.** The Arbitration Committee is the last step, and it rules on editors' conduct, not on content ([Signpost, May 2023](https://signpost.news/2023-05-22/Arbitration_report)). The earlier steps (talk page, noticeboards, requests for comment) are **(unverified)** from the policy pages.
- **Finnish Wikipedia.** [Wikipedia:Muokkaussota](https://fi.wikipedia.org/wiki/Wikipedia:Muokkaussota) and the protection policy could not be loaded. **(unverified)**: whether fi-wiki has a formal three-revert rule, and its protection levels. What we could confirm about fi-wiki:
  - It uses FlaggedRevs (one of the 17 editions studied), where edits by untrusted users are reviewed and readers can be shown the last reviewed version ([Tran et al. 2022](https://arxiv.org/pdf/2202.05548)). fi-wiki's exact configuration is **(unverified)**.
  - It has `fiwiki-damaging` and `fiwiki-goodfaith` models on Lift Wing ([Wikitech](https://wikitech.wikimedia.org/wiki/Machine_Learning/LiftWing)).

## 2. How research detects and measures edit wars

All SQL below is a sketch and untested. It assumes the starter's table, where `row_start` is the edit time.

- **Identity revert (Halfaker, `mwreverts`).** A version whose text is identical to an earlier one; everything in between was reverted. The library looks back 15 versions by default ([Research:Revert](https://webcf.waybackmachine.org/web/20210818173454/https://meta.wikimedia.org/wiki/Research:Revert)). The starter does this without the look-back limit.
  - *Weaknesses:* checksums find about 94% of reverts; about 6% of identity reverts are pseudo-reverts such as blanking; 9% are self-reverts and 11% edit wars, so "reverted" does not mean "bad" (same page). The method cannot tell full from partial reverts ([Flöck et al. 2012](https://eprints.soton.ac.uk/351610)).

```sql
WITH v AS (SELECT page_id, rev_id, user, sha1, row_start,
             ROW_NUMBER() OVER (PARTITION BY page_id ORDER BY row_start) AS n
           FROM article FOR SYSTEM_TIME ALL)
SELECT r.page_id, r.rev_id AS reverting, r.user AS reverter,
       x.rev_id AS reverted, x.user AS reverted_user,
       TIMESTAMPDIFF(SECOND, x.row_start, r.row_start) AS survived_s
FROM v r
JOIN v t ON t.page_id = r.page_id AND t.sha1 = r.sha1
        AND t.n BETWEEN r.n - 15 AND r.n - 2      -- keep the nearest t only
JOIN v x ON x.page_id = r.page_id AND x.n > t.n AND x.n < r.n
WHERE x.user <> r.user AND x.sha1 <> r.sha1;      -- drop self-reverts
```

- **Kittur et al. 2007, "He says, she says".**
  - *Article level:* a model on 30 history statistics predicted how often an article carried the {{controversial}} tag (R² = 0.897). Talk-page activity was the strongest predictor ([paper](https://www.gwern.net/doc/wikipedia/2007-kittur.pdf)).
  - *User level:* a "Revert Graph" links each reverter to the editor reverted, and the sides appear as clusters (Dokdo, Terri Schiavo).
  - *SQL:* `GROUP BY reverter, reverted_user` on the query above gives the edges. They also counted edit summaries containing "revert" or "rv" to catch partial reverts: use `comment LIKE` with the Finnish equivalents, read off the data.
  - *Weaknesses:* talk pages are not in the dataset; the model mixes conflict with vandalism and with fast-moving news.
- **Controversy measure M** ([Sumi et al. 2011](https://arxiv.org/pdf/1107.3689); [Yasseri et al. 2012](https://arxiv.org/pdf/1202.3643)).
  - *Method:* take mutual reverts only. Weight each by the smaller of the two editors' edit counts, so a veteran undoing a drive-by vandal counts for almost nothing. Drop the single heaviest pair, so a two-person feud does not count. Sum, then multiply by the number of editors involved in mutual reverts.
  - *SQL:* self-join the revert pairs on `(a,b) = (b,a)`, join a per-user `COUNT(*)`, take `SUM(LEAST(n_a, n_b)) * COUNT(DISTINCT user)`.
  - *Validation:* 27% of pages at M = 50 were judged controversial, 97% at M ≥ 5,600. With M > 1,000 as the cut-off, under 1% of English articles were controversial ([Sumi et al.](https://arxiv.org/pdf/1107.3689)).
  - *Patterns over time:* consensus; a sequence of temporary consensuses, with wars about 1,300 edits apart on average; never-ending war ([Yasseri et al. 2012](https://arxiv.org/pdf/1202.3643)). The second is the "slow edit war" that a 24-hour rule and a monthly threshold both miss.
  - *Weaknesses:* recall was never measured; thresholds were tuned on English and must be recalibrated; the PDF text of the formula was garbled in extraction, so check the notation before quoting it.
- **Yasseri et al. 2014, multilingual.** M applied to English, German, French, Spanish, Persian, Czech, Hungarian, Arabic, Romanian and Hebrew. **Finnish is not covered.** Politics, countries and religion made up more than half of the top lists ([paper](https://arxiv.org/pdf/1305.5566)).
- **WikiWho / TokTrack.** Tracks every word: the version that added it and every version that removed or re-added it; 13.5 billion tokens for English up to October 2016 ([Flöck et al. 2017](https://arxiv.org/abs/1703.08244)). This catches partial reverts. It needs a diff per version pair, so it is done in application code, not SQL.
- **Contropedia.** Splits versions into sentences, discards vandalism, counts edits that *delete or replace* text in a sentence, and assigns the score to the wiki links in it. Shown as a heat layer on the article and a ranked dashboard ([Borra et al. 2015](https://arxiv.org/pdf/1904.08721)). Its vandalism filter is directly reusable: "vandal" in the revert comment, known bot names, or an IP edit reverted within 60 seconds.

## 3. Vandalism

- **How much.** On English Wikipedia up to 2006, vandalism-tagged edits were 1–2% of edits and reverts about 6.7% ([Kittur et al. 2007](https://www.gwern.net/doc/wikipedia/2007-kittur.pdf)). In 2022 data from 47 languages, about 7% of edits were reverted, and 28% in the anonymous-only set ([Trokhymovych et al. 2023](https://arxiv.org/pdf/2306.01650)).
- **How fast.** 577,643 vandal edits: median survival 11.3 minutes, mean 2.1 days, so a long tail ([Kittur et al. 2007](https://www.gwern.net/doc/wikipedia/2007-kittur.pdf)). About half of damage is fixed within one or two page views, 11% lasts beyond 100 views, and 0.37% of views saw a damaged page ([Priedhorsky et al. 2007, via Signpost](https://signpost.news/2007-10-08/Vandalism_study); secondary).
- **Who catches it.** When the bot ClueBot NG was down in 2011, median time to revert rose from 12.4 to 21.4 minutes; the damage was still caught, but later ([Geiger & Halfaker 2013](https://stuartgeiger.com/files/wikisym13-cluebot.pdf)). ClueBot NG is an English Wikipedia bot; whether fi-wiki has an equivalent is **(unverified)**.
- **Models.** ORES `damaging` and `goodfaith` separate harmful edits from honest mistakes; 110 classifiers for 44 languages; filtering can cut patrol work by about 90% ([Halfaker & Geiger 2020](https://arxiv.org/pdf/1909.05189)). They now run on Lift Wing, and **fi-wiki has both** ([Wikitech](https://wikitech.wikimedia.org/wiki/Machine_Learning/LiftWing)). The newer Revert Risk model covers 47 languages; whether Finnish is one could not be confirmed ([Trokhymovych et al. 2023](https://arxiv.org/pdf/2306.01650)).
- **What lingers.**
  - Low-traffic pages: 90% of hoax articles are flagged within an hour, but 1 in 100 survives over a year, and long-lived ones get a median of 3 views a day ([Kumar et al. 2016](https://dlab.epfl.ch/people/west/pub/Kumar-West-Leskovec_WWW-16.pdf)).
  - History on smaller wikis: one editor wrote 206 fictional articles on Qing and Russian history on Chinese Wikipedia over 10 years ([Sixth Tone, 2022](https://www.sixthtone.com/news/1010653/She%20Spent%20a%20Decade%20Writing%20Fake%20Russian%20History.%20Wikipedia%20Just%20Noticed.)).
  - Review capacity: the median wait for review of an IP edit was 2 hours on German Wikipedia and over 13 days on Russian ([Tran et al. 2022](https://arxiv.org/pdf/2202.05548)). fi-wiki's figure is not given.
- **Finnish example.** Yle described a short-lived vandal edit to the article on Li Andersson, and cited a 2013 Helsingin Sanomat test in which 70% of 134 fi-wiki articles rated good or excellent on facts ([Yle, 2016](https://yle.fi/a/20-167264)).
- **Temporary accounts.**
  - IPs of logged-out editors are no longer public. The name starts with `~` and the year of the first edit, such as `~2024-12345-67` ([Help:Temporary accounts](https://www.mediawiki.org/wiki/Help:Temporary_accounts)).
  - Rollout: 12 pilot wikis first ([mediawiki.org](https://www.mediawiki.org/wiki/Trust_and_Safety_Product/Temporary_Accounts)), then over a thousand wikis, then English Wikipedia, planned for 4 November 2025 ([Signpost, Oct 2025](https://signpost.news/Single/2025-10-20); [Nov 2025](https://signpost.news/2025-11-10/News_and_notes)). The fi-wiki date is **(unverified)**; the starter README reports 70 such accounts in its 50 articles.
  - Only admins and a "temporary account IP viewer" group can see the IP ([Signpost, Oct 2025](https://signpost.news/Single/2025-10-20)).
  - For analysis: no grouping by IP range after the switch. Accounts expire, so one person becomes several "editors" (after one year per the Help page as read; 90 days is also reported, **unverified**). Older edits still show IPs, so per-editor counts are not comparable across the switch. Check that the dataset's `anonymous` flag covers both IPs and `~` names.

## 4. The actual harms

**Readers**

- No signal. Maintenance banners target editors and many readers are unaware of them. A simple trust gauge moved reader trust in both directions, and a "disputed references" notice lowered it by 1.6 points on a 7-point scale ([Kuznetsov et al. 2022](https://par.nsf.gov/servlets/purl/10358961)).
- The reader sees whichever version was saved last, or last reviewed where FlaggedRevs applies ([Tran et al. 2022](https://arxiv.org/pdf/2202.05548)).

**Editors**

- Good-faith newcomers whose first edits were reverted rose from 6.1% to 18.2% between 2006 and 2007, and their survival fell from 25.6% to 11.7%. Reverts by tools hurt most, and Huggle users joined a follow-up discussion about 7% of the time ([Halfaker et al. 2013](https://stuartgeiger.com/papers/abs-rise-and-decline-wikipedia.pdf)).
- Editors on war articles describe burnout and attacks on them personally ([Kurek et al. 2024](https://arxiv.org/html/2409.02304v1)).
- Research on why very active editors leave centres on interpersonal conflict and overload, especially for admins. A survey of the 300 most active editors (41% response) calls for more work on conflict as a reason for retiring; the review gives no figure ([Konieczny 2018, via Signpost](https://signpost.news/2018-12-01/Recent_research); secondary).
- Patrol workload: reviewing every edit by hand was estimated at 483 hours of work a day ([Halfaker & Geiger 2020](https://arxiv.org/pdf/1909.05189)).

**History topics**

- *Croatian Wikipedia.* From at least 2011 to 2020 a small group of admins introduced far-right bias and disinformation, and reverted and blocked dissenters; Serbian Wikipedia largely avoided this ([Kharazian et al. 2023](https://arxiv.org/abs/2311.03616)). The Wikimedia Foundation's own [2021 assessment](https://meta.wikimedia.org/wiki/Croatian_Wikipedia_Disinformation_Assessment-2021) could not be loaded **(unverified first-hand)**.
- *Holocaust in Poland, English Wikipedia.* Grabowski and Klein examined 25 articles and nearly 300 back-end pages and argue that a small group of editors distorted the history ([abstract](https://digitalcommons.chapman.edu/history_articles/74), 9 Feb 2023). The editors named dispute its accuracy ([Signpost, Mar 2023](https://signpost.news/2023-03-09/Recent_research)). The arbitration case ended on 20 May 2023 with three topic bans and a stricter sourcing rule ([Signpost, May 2023](https://signpost.news/2023-05-22/Arbitration_report)).
- *Russia-Ukraine.* 86 since-blocked accounts made 681 edits to the English Russo-Ukrainian War article; the authors do not attribute them to a state ([ISD/CASM 2022](https://files.casmtechnology.com/information-warfare-and-wikipedia_v2.pdf); [The Record](https://therecord.media/researchers-wikipedia-a-front-in-russian-propaganda-war/)).
- *Language editions diverge.* For one medieval battle, only 2 of 119 citations were shared across editions ([Creanga et al. 2026](https://aclanthology.org/2026.nlperspectives-1.2/)).

**Finnish history: no evidence found**

- We found no study, WMF report or press article documenting edit wars or ideological distortion on Finnish Wikipedia's history articles: not on the name of the 1918 war, the Continuation War, Karelia or Mannerheim. The ISD/CASM report does not mention Finland, and Yasseri et al. did not include Finnish.
- What is documented is that the *topic* is contested. School textbooks moved from "vapaussota" (until the 1950s) to "kansalaissota" (1960s) to "sisällissota" (mid-1990s), each name carrying a viewpoint ([University of Helsinki, 2018](https://www.helsinki.fi/fi/uutiset/yhteiskunta-ja-oppiminen/punakaartilaiskapina-ja-sisallissota-vuoden-1918-sodan-nimityksia-opetuksessa-ovat-muokanneet-kaunokirjallisuus-ja-historiantutkimus)).
- So the honest pitch is "we measured it", not "it is known". The data is there: *Suomen sisällissota* has 3,357 versions and *Talvisota* 328 reverts ([starter README](https://github.com/MariaDB/mariadb-system-versioning-wikipedia)).

## 5. Existing tools and their gaps

| Tool | What it gives | Gap |
|---|---|---|
| Page history and diff | Every version, pairwise diff | Flat list; no view of one passage over time |
| XTools | Counts: revisions, editors, creation date, pageviews ([mediawiki.org](https://www.mediawiki.org/wiki/XTools)) | Nothing on reverts or disputes on the page read; the full statistics page could not be loaded |
| WikiWho API, Who Wrote That | Origin and change history of every token; **Finnish is supported** (70 editions) ([WikiWho API](https://wikiwho-api.wmcloud.org/)) | Raw provenance only; no dispute view, no meaning. Who Wrote That's page could not be loaded **(unverified)** |
| Contropedia | Contested wiki links, heat layer, timeline ([site](https://contropedia.net)) | English only; site says "still working on this"; talk pages never linked ([paper](https://arxiv.org/pdf/1904.08721)) |
| Protection log | When a page was locked | Incomplete and inconsistent, especially before September 2008 ([Hill & Shaw 2015](https://opensym.cs.fau.de/os2015/proceedings-files/p403-hill.pdf)); not in the dataset |

**What nobody can easily find out today:** which sentences of the current article have been fought over; whether a revert was a dispute or cleanup; whether a quiet article has a slow war running for years; what the disagreement is *about*, in words; whether the same dispute runs across many articles; how long bad text stayed up.

## 6. Ethics and limits: guidance for the demo

- **Label edits, not people.** Show "Editor A / Editor B" by default and link to the public version. Do not print "vandal" or "edit warrior" next to a user name.
- **Reverted is not bad, anonymous is not vandal.** Reverts include self-reverts and disputes ([Research:Revert](https://webcf.waybackmachine.org/web/20210818173454/https://meta.wikimedia.org/wiki/Research:Revert)). About 80% of newcomers were good-faith ([Halfaker et al. 2013](https://stuartgeiger.com/papers/abs-rise-and-decline-wikipedia.pdf)). Vandalism models are measurably biased against anonymous editors ([Trokhymovych et al. 2023](https://arxiv.org/pdf/2306.01650)).
- **IPs.** The Foundation hid them because they can reveal location and identity ([mediawiki.org](https://www.mediawiki.org/wiki/Trust_and_Safety_Product/Temporary_Accounts)). Do not geolocate old IPs or try to link temporary accounts to each other.
- **Naming has consequences.** A paper that named editors led to a months-long arbitration case and a public dispute over its accuracy ([Signpost, Mar 2023](https://signpost.news/2023-03-09/Recent_research)).
- **Missing data.** Versions hidden by admins are not in the dumps ([starter README](https://github.com/MariaDB/mariadb-system-versioning-wikipedia)), and neither are talk pages or review status.
- **Licence.** CC BY-SA 4.0: give credit, link the licence, say if you changed the text, and share derivatives under the same licence ([CC deed](https://creativecommons.org/licenses/by-sa/4.0/deed.en)). Link every quoted passage to its version (`?oldid=rev_id`) and mark machine summaries as machine-made.
- **Say what the score is.** "Mutual reverts by sha1; partial reverts not counted."

## 7. Feature ideas beyond the starter

1. **Contested-passage heatmap.** Split each version into paragraphs and keep one row per paragraph in a system-versioned `passage` table. `row_start` and `row_end` are then each paragraph's lifetime, and a paragraph that keeps dying and returning is contested. Colour today's article by it. *Demo: high, the centrepiece.* Paragraph hashing is cruder than WikiWho's tokens; say so.
2. **"What is this fight about?"** Embed removed and re-added passages in a `VECTOR` column, cluster by cosine distance, and let an LLM summarise each cluster with links to the versions ([MariaDB Vector](https://mariadb.com/docs/server/reference/sql-structure/vectors/vector-overview)). This is the one place vector search truly helps: the same dispute is reworded each round, so hashes miss it. Add the word pairs that flip, such as *vapaussota* and *sisällissota*. *Demo: high.* Keep vectors in a separate plain table; a vector index on a versioned table is **(unverified)**.
3. **Dispute score, not revert count.** M per article and per year over all 19,742 articles, as a ranked list. *Demo: high, one query, and new for Finnish.*
4. **Slow edit wars.** Find text states (sha1, or paragraph hashes from idea 1) that return three or more times with gaps of weeks or months, and editor pairs with mutual reverts spread over years. *Demo: medium-high.*
5. **Vandalism survival time.** `survived_s` from the query in section 2: median and tail by year and by anonymous or named, plus the longest-lived later-reverted edits. Compare with 11.3 minutes (English, 2006). *Demo: high.* Caveat: with FlaggedRevs, readers may never have seen the edit.
6. **Reader stability view.** `FOR SYSTEM_TIME AS OF` plus paragraph age: "unchanged since 2014" or "changed 14 times this year". Offer the longest-lived recent version as a "stable version". *Demo: high*, and it answers the missing reader signal.
7. **Who-versus-who graph, pseudonymised.** Kittur's Revert Graph: nodes are editors, edges are reverts, clusters are sides, labelled Side A and Side B. *Demo: medium*, needs a graph layout.
8. **Protection before and after.** If protection events can be found in the edit summaries **(unverified)**, compare reverts and anonymous edits 30 days either side. *Demo: medium, riskiest.*

## Sources

Read first-hand unless noted.

- Borra et al. *Societal Controversies in Wikipedia Articles* (Contropedia), CHI 2015. https://arxiv.org/pdf/1904.08721 · https://contropedia.net
- Creanga, Dinu, Dinu. *The Rashomon Wikipedia*, NLPerspectives 2026. https://aclanthology.org/2026.nlperspectives-1.2/
- Flöck, Erdogan, Acosta. *TokTrack*, 2017. https://arxiv.org/abs/1703.08244 · WikiWho API: https://wikiwho-api.wmcloud.org/
- Flöck, Vrandečić, Simperl. *Revisiting Reverts*, 2012 (abstract only). https://eprints.soton.ac.uk/351610
- Geiger & Halfaker. *When the Levee Breaks*, WikiSym 2013. https://stuartgeiger.com/files/wikisym13-cluebot.pdf
- Grabowski & Klein. *Wikipedia's Intentional Distortion of the History of the Holocaust*, 2023 (abstract only). https://digitalcommons.chapman.edu/history_articles/74
- Halfaker & Geiger. *ORES*, 2020. https://arxiv.org/pdf/1909.05189
- Halfaker, Geiger, Morgan, Riedl. *The Rise and Decline of an Open Collaboration System*, 2013. https://stuartgeiger.com/papers/abs-rise-and-decline-wikipedia.pdf
- Hill & Shaw. *Page Protection: Another Missing Dimension of Wikipedia Research*, OpenSym 2015. https://opensym.cs.fau.de/os2015/proceedings-files/p403-hill.pdf
- Kharazian, Starbird, Hill. *Governance Capture in a Self-Governing Community*, 2023 (abstract). https://arxiv.org/abs/2311.03616
- Kittur, Suh, Pendleton, Chi. *He Says, She Says*, CHI 2007. https://www.gwern.net/doc/wikipedia/2007-kittur.pdf
- Kumar, West, Leskovec. *Disinformation on the Web*, WWW 2016. https://dlab.epfl.ch/people/west/pub/Kumar-West-Leskovec_WWW-16.pdf
- Kurek, Budak, Gilbert. *Wikipedia in Wartime*, 2024. https://arxiv.org/html/2409.02304v1
- Kuznetsov et al. *Templates and Trust-o-meters*, CHI 2022. https://par.nsf.gov/servlets/purl/10358961
- Miller et al. *Information Warfare and Wikipedia*, ISD/CASM 2022. https://files.casmtechnology.com/information-warfare-and-wikipedia_v2.pdf
- Sumi, Yasseri, Rung, Kornai, Kertész. *Edit Wars in Wikipedia*, 2011. https://arxiv.org/pdf/1107.3689
- Tran, Champion, Hill, Greenstadt. *Prepublication Moderation: Evidence from 17 Wikipedia Language Editions*, 2022. https://arxiv.org/pdf/2202.05548
- Trokhymovych et al. *Fair Multilingual Vandalism Detection System for Wikipedia*, 2023. https://arxiv.org/pdf/2306.01650
- Yasseri, Sumi, Rung, Kornai, Kertész. *Dynamics of Conflicts in Wikipedia*, 2012. https://arxiv.org/pdf/1202.3643
- Yasseri, Spoerri, Graham, Kertész. *The Most Controversial Topics in Wikipedia*, 2014. https://arxiv.org/pdf/1305.5566
- Research:Revert (Wikimedia Meta), archive copy of 18 Aug 2021. https://webcf.waybackmachine.org/web/20210818173454/https://meta.wikimedia.org/wiki/Research:Revert
- mediawiki.org: [Temporary Accounts](https://www.mediawiki.org/wiki/Trust_and_Safety_Product/Temporary_Accounts) · [Help:Temporary accounts](https://www.mediawiki.org/wiki/Help:Temporary_accounts) · [XTools](https://www.mediawiki.org/wiki/XTools) · Wikitech [Lift Wing](https://wikitech.wikimedia.org/wiki/Machine_Learning/LiftWing)
- The Signpost: [Vandalism study, 2007](https://signpost.news/2007-10-08/Vandalism_study) · [Recent research, Dec 2018](https://signpost.news/2018-12-01/Recent_research) · [Recent research, Mar 2023](https://signpost.news/2023-03-09/Recent_research) · [Arbitration report, May 2023](https://signpost.news/2023-05-22/Arbitration_report) · [20 Oct 2025](https://signpost.news/Single/2025-10-20) · [10 Nov 2025](https://signpost.news/2025-11-10/News_and_notes)
- Yle. *Voiko Wikipediaan luottaa?*, 2016. https://yle.fi/a/20-167264
- University of Helsinki, names of the 1918 war, 2018. https://www.helsinki.fi/fi/uutiset/yhteiskunta-ja-oppiminen/punakaartilaiskapina-ja-sisallissota-vuoden-1918-sodan-nimityksia-opetuksessa-ovat-muokanneet-kaunokirjallisuus-ja-historiantutkimus
- Sixth Tone, Zhemao hoaxes, 2022. https://www.sixthtone.com/news/1010653/She%20Spent%20a%20Decade%20Writing%20Fake%20Russian%20History.%20Wikipedia%20Just%20Noticed.
- Creative Commons BY-SA 4.0 deed. https://creativecommons.org/licenses/by-sa/4.0/deed.en
- MariaDB Vector overview. https://mariadb.com/docs/server/reference/sql-structure/vectors/vector-overview
- Starter demo README (MariaDB Foundation, Oct 2026). https://github.com/MariaDB/mariadb-system-versioning-wikipedia
- **Not loaded, linked for the team to check:** [WP:Edit warring](https://en.wikipedia.org/wiki/Wikipedia:Edit_warring) · [Wikipedia:Muokkaussota](https://fi.wikipedia.org/wiki/Wikipedia:Muokkaussota) · [Croatian Wikipedia Disinformation Assessment 2021](https://meta.wikimedia.org/wiki/Croatian_Wikipedia_Disinformation_Assessment-2021)
