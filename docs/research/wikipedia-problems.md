# Current Wikipedia problems a MariaDB RAG/SVT tool could help with

Researched 2026-11-13 for the Junction MariaDB challenge (Finnish Wikipedia, history of Finland). Most claims link to first-party sources: WMF research, WMF posts and peer-reviewed or arXiv papers. Some links are secondary and are marked that way. Wikimedia pages could not be fetched reliably from the research environment. Live backlog-category counts (en and fi) could not be read and are marked **unverified**. The team should check them live before quoting them in the pitch.

## TL;DR: most promising for this hackathon

1. **Claims that their cited source doesn't support (verifiability).** About 30% of article-body claims aren't supported by their accessible cited source, and in >40% of checked cases the reference held no evidence for the claim ([Walden et al. 2025](https://arxiv.org/abs/2506.12637v1), [Petroni et al. / SIDE](https://arxiv.org/pdf/2207.06220)). *Why here:* it's a natural RAG demo (claim → vector-retrieve the source passage → support / no support), and it helps both readers and editors.
2. **Growing "citation needed" backlog.** The number of en-wiki articles with a {{Citation needed}} tag grew from >350k (Feb 2019) to >550k (Sep 2025) ([Redi et al. 2019](https://arxiv.org/pdf/1902.11116), [Baigutanova et al. 2026](https://arxiv.org/html/2603.17146v1)). *Why here:* RAG can suggest candidate sources from the corpus, and SVT can show when a claim lost its citation or when the tag was added.
3. **Article history is hard to see.** Only research tools such as [WikiWho/TokTrack](https://arxiv.org/abs/1703.08244) answer questions like "who wrote this sentence, what was removed, what keeps being re-added". Contested Finnish history topics (the 1918 war has 10+ names, [Vapriikki](https://tampere1918.fi/en/war/the-many-names-of-the-finnish-civil-war/)) make this vivid. *Why here:* it's the core SVT use case (`FOR SYSTEM_TIME AS OF`, diffs, revert detection) and very easy to demo.
4. **Readers want short answers from long, hard-to-read articles, and are getting them from AI elsewhere.** 38% of reader sessions are quick fact look-ups and 39% want an overview ([Singer et al. 2017](https://arxiv.org/pdf/1702.05379)). Text is around US grade 9+ in most languages ([Trokhymovych et al. 2024](https://arxiv.org/html/2406.01835v1)). Human pageviews fell about 8% year over year in 2025, which WMF attributes to generative AI and social media ([WMF Diff, Oct 2025](https://diff.wikimedia.org/2025/10/17/new-user-trends-on-wikipedia/)). *Why here:* a cited, Finnish-language Q&A answers the reader need without losing attribution. WMF's own call is "platforms should make it clear where the information is sourced from."
5. **Editor overload (fewer newcomers, more AI-generated text to patrol).** New registrations fell 36% between 2016 and 2025 ([Signpost, Jan 2026](https://signpost.news/2026-01-15/Special_report)). WMF's AI strategy names moderators and patrollers as its first priority ([WMF, Apr 2025](https://wikimediafoundation.org/news/2025/04/30/our-new-ai-strategy-puts-wikipedias-humans-first/), via [Nieman Lab](https://www.niemanlab.org/2025/04/wikipedia-announces-new-ai-strategy-to-support-human-editors/)). *Why here:* it frames items 1–3 as tools that save editors time, which is what WMF itself is asking for.

**Best combo pitch:** one tool that does both. An SVT edit-history layer and a RAG layer over the same MariaDB, giving a "cited answer, plus how this answer changed over time and which of its claims are actually backed."

---

## 1. Citation verifiability: does the source support the claim?

- **What:** A footnote exists, but the cited source doesn't say what the sentence claims, or says it only partly.
- **Evidence:**
  - About 22% of lead-section claims aren't supported by the article body, and about 30% of body claims aren't supported by their publicly accessible cited sources ([Walden et al., arXiv, Jun 2025](https://arxiv.org/abs/2506.12637v1)).
  - In the Meta AI SIDE paper, "more than 40% of the time no evidence can be found in the reference to verify a Wikipedia claim." For the 10% of citations the model most suspected, humans preferred its suggested replacement 70% of the time ([Petroni et al., arXiv 2207.06220](https://arxiv.org/pdf/2207.06220); later in *Nature Machine Intelligence* 2023, [PDF](https://www.nature.com/articles/s42256-023-00726-1.pdf)).
  - Readers rarely check: only 0.29% of page views include a reference click, and clicks are more likely on short or low-quality articles ([Piccardi et al., WWW 2020](https://arxiv.org/abs/2001.08614v1)).
- **Who it hurts:** Readers, who trust footnotes they never open. Editors, who can't check sources at scale.
- **MariaDB angle (RAG):** Chunk and embed the cited sources (or the corpus's own reference texts) into a `VECTOR` column. For each sentence, retrieve the top-k passages and have an LLM label them supported / partial / not found, showing the evidence quote. SVT can then flag when a claim was edited after its citation was added, so the claim drifted away from its source.
- **Demo-ability:** High. Highlight sentences in green/amber/red on a Finnish history article and click one to see the evidence passage. Caveat: the source texts are needed, and many cited Finnish history books are offline. Use web sources and Wikipedia-internal consistency (lead vs body) as a fallback.

## 2. Unsourced statements / "citation needed" backlog

- **What:** Statements that need a source but have none, tagged or untagged.
- **Evidence:**
  - en-wiki articles with at least one {{Citation needed}} tag: >350,000 in Feb 2019 ([Redi et al., WWW 2019](https://arxiv.org/pdf/1902.11116)) and >550,000 by Sep 2025 ([Baigutanova et al., WMF, 2026](https://arxiv.org/html/2603.17146v1)). That is roughly +57% in 6.5 years.
  - Even in featured articles, about 43% of English and about 78% of German sentences are uncited (not all of them need a citation) (same WMF paper).
  - WMF is building a multilingual "reference need" model, so this is a live, first-party priority (same paper). Finnish is not among its evaluated languages.
  - fi-wiki has the maintenance category [Luokka:Lähteettömät artikkelit](https://fi.wikipedia.org/wiki/Luokka:L%C3%A4hteett%C3%B6m%C3%A4t_artikkelit) (articles with no sources) and the maintenance hub [Wikipedia:Huomiota kaipaavat sivut](https://fi.wikipedia.org/wiki/Wikipedia:Huomiota_kaipaavat_sivut). **Unverified:** current counts could not be read. Check them live.
  - The [Citation Hunt](https://meta.wikimedia.org/wiki/Citation_Hunt) tool exists for fixing these one at a time, but it only surfaces snippets and doesn't suggest sources.
- **Who it hurts:** Editors (the backlog). Readers (unverifiable claims).
- **MariaDB angle:** RAG suggests candidate sources or supporting passages from the corpus for each tagged sentence ("Citation Hunt with suggestions"). SVT answers when the tag was added, whether the sentence ever had a citation, and who removed it.
- **Demo-ability:** High. A backlog dashboard for the dataset, plus a "fix it" button that proposes a source.

## 3. Hard-to-see article history, edit wars and contested framing

- **What:** The history page is a flat list of diffs. Readers and even editors can't easily answer "how did this paragraph evolve", "what was deleted", or "is this article being fought over".
- **Evidence:**
  - Answering provenance questions needed dedicated research infrastructure: TokTrack/WikiWho tracked 13.5 billion token instances to show which revision created, deleted and re-added each word ([Flöck et al. 2017](https://arxiv.org/abs/1703.08244)). This is not part of the standard Wikipedia UI.
  - Controversy can be measured from mutual reverts. A study of 10 language editions found top-100 "most controversial" lists that vary across languages ([Yasseri et al. 2014](https://arxiv.org/abs/1305.5566)).
  - Reverts hurt retention: good-faith newcomers increasingly had their first edits reverted, and this predicts the decline. Tool-assisted reverters joined discussion about 7% of the time vs about 60% for manual reverts ([Halfaker et al. 2013](https://meta.wikimedia.org/wiki/Research:The_Rise_and_Decline)).
  - Finnish history example: the 1918 war is called civil war, *vapaussota*, *kansalaissota*, revolution, red rebellion, class war, and other names, each reflecting a side ([Vapriikki / Tampere 1918 museum](https://tampere1918.fi/en/war/the-many-names-of-the-finnish-civil-war/)). This is ideal for showing terminology drift across revisions. **Unverified:** whether fi-wiki had actual edit wars over this naming.
- **Who it hurts:** Readers (no context on how settled a claim is). Editors and patrollers (spotting wars late).
- **MariaDB angle (SVT):** Store revisions in a system-versioned table. Use `FOR SYSTEM_TIME AS OF '2010-01-01'` for a "time travel" view, `BETWEEN` for a churn timeline, and a revert detector (identical content hash reappearing) to compute a per-section controversy score. RAG can then answer "how has this article's description of 1918 changed?" with cited revisions.
- **Demo-ability:** Very high. A time slider over an article, a heatmap of contested sections, and a "removed text" panel.

## 4. Reader information overload, readability, and natural-language questions

- **What:** Most readers want a fact or an overview, but articles are long and dense, and in-wiki search is keyword-based.
- **Evidence:**
  - Reading needs: 38% quick fact look-up, 39% overview, 21% in-depth. 47% of readers are unfamiliar with the topic ([Singer et al., WWW 2017](https://arxiv.org/pdf/1702.05379), about 30k survey responses).
  - Readability: across 24 language samples, median text difficulty is roughly US grade 9 or higher. "Poor readability found in English Wikipedia generalizes to most other language editions" ([Trokhymovych, Sen, Gerlach, ACL 2024](https://arxiv.org/html/2406.01835v1)). Finnish was not in their training set.
  - Sessions are shallow: 78% are a single page load, and about 78% of incoming traffic comes from search engines ([Piccardi & West 2025](https://arxiv.org/pdf/2501.00939)).
  - Scale: English Wikipedia is >5 billion words ([Pew, Jan 2026](https://www.pewresearch.org/short-reads/2026/01/13/wikipedia-at-25-what-the-data-tells-us/), secondary analysis of WMF data).
  - WMF trialled AI "Simple Article Summaries" on mobile and paused it in June 2025 after editor objections ([MediaWiki project page](https://www.mediawiki.org/wiki/Reading/Web/Content_Discovery_Experiments/Summaries), could not be fetched; [press summary](https://tech.yahoo.com/ai/articles/wikipedia-pauses-ai-summaries-pushback-092847335.html)). Lesson: summaries without verifiable citations get rejected by editors.
- **Who it hurts:** Readers.
- **MariaDB angle (RAG):** Finnish natural-language Q&A over the corpus, with every sentence of the answer linked to a paragraph and revision ID. Hybrid search (MariaDB `VECTOR` plus full-text index) beats keyword search. Showing the revision ID answers the editors' objection: the summary stays verifiable.
- **Demo-ability:** High, and the most "wow" for judges. Risk: it's the most common hackathon idea, so the citation-per-sentence and history hook is what differentiates it.

## 5. AI search eroding traffic and attribution (the sustainability loop)

- **What:** People get Wikipedia's content through AI answers and search snippets without visiting, which reduces donations and the pool of potential editors.
- **Evidence:**
  - Human pageviews fell roughly 8% compared with the same months of 2024, after WMF reclassified bot traffic that had been built to evade detection (Mar–Aug 2025). WMF: "these declines reflect the impact of generative AI and social media" ([WMF Diff, 17 Oct 2025](https://diff.wikimedia.org/2025/10/17/new-user-trends-on-wikipedia/), read via mirror).
  - Total pageviews went from 194B (2016) to 177B (2025) while internet users rose 83% ([Signpost special report, Jan 2026](https://signpost.news/2026-01-15/Special_report), an opinion essay by a former WMF board chair that uses stats.wikimedia.org data).
  - In 2025, more than 88B views came from crawlers, AI bots and other non-human agents ([Pew, Jan 2026](https://www.pewresearch.org/short-reads/2026/01/13/wikipedia-at-25-what-the-data-tells-us/)).
- **Who it hurts:** The whole ecosystem. Readers too, through less maintenance.
- **MariaDB angle:** Build the "good citizen" RAG that WMF asks for. Every answer deep-links to the article section and revision, and the links count as returns to Wikipedia. It's a framing more than a feature.
- **Demo-ability:** Medium. It works best as a slide that motivates #4.

## 6. Shrinking contributor pipeline and newcomer retention

- **What:** Fewer new editors, and the remaining editors are more loaded.
- **Evidence:**
  - en-wiki active editors (5+ edits/month) peaked in early 2007, then declined linearly ([Halfaker et al. 2013](https://meta.wikimedia.org/wiki/Research:The_Rise_and_Decline)).
  - New registered users per month fell from 317k (2016) to 202k (2025), down 36%, while edits rose 37%, so each new user carries more edits ([Signpost, Jan 2026](https://signpost.news/2026-01-15/Special_report); the metric is disputed on its talk page).
  - WMF's 2025 AI strategy targets "guided mentorship" for newcomers and AI-assisted workflows for moderators and patrollers. It warns that managing AI-assisted content "risks burnout" ([WMF, 30 Apr 2025](https://wikimediafoundation.org/news/2025/04/30/our-new-ai-strategy-puts-wikipedias-humans-first/), quoted via [Nieman Lab](https://www.niemanlab.org/2025/04/wikipedia-announces-new-ai-strategy-to-support-human-editors/)).
  - Finnish Wikipedia has about 625k articles and reached 600k on 11 Aug 2025 ([en-wiki: Finnish Wikipedia](https://en.wikipedia.org/wiki/Finnish_Wikipedia)). **Unverified:** fi-wiki active-editor counts and trend (stats.wikimedia.org was not reachable). Pull them from [stats.wikimedia.org](https://stats.wikimedia.org/#/fi.wikipedia.org) for the pitch.
- **Who it hurts:** Editors, and readers downstream as backlogs grow.
- **MariaDB angle:** Mostly a motivation. Concrete versions: a newcomer "task feed" (unsourced sentences with RAG-suggested sources, see #2), and an SVT "why was my edit reverted" view showing what changed and which comparable edits survived.
- **Demo-ability:** Medium.

## 7. AI-generated content entering Wikipedia (knowledge integrity)

- **What:** LLM-written articles with weak or fabricated sourcing.
- **Evidence:**
  - Detectors flag more than 5% of new en-wiki articles created in Aug 2024 as AI-generated (4.36% net of baseline). Flagged articles have fewer references and fewer links ([Brooks et al., WikiNLP 2024](https://arxiv.org/html/2410.08044v1)).
  - Wikipedia added a speedy-deletion criterion for "unreviewed machine-generated content" in 2025. heise calls it A9 and describes it as covering chatbot phrasing and invented sources ([heise, 2025](https://heise.de/-10510852), secondary). Press reports call the en-wiki version G15. **Unverified:** exact criterion number, wiki and adoption date, because the policy page couldn't be fetched.
- **Who it hurts:** Editors (patrol load). Readers (fabricated claims).
- **MariaDB angle:** SVT tracks large single-revision insertions and how much of that text survives. RAG checks each inserted claim against the corpus and cited sources (reuses #1).
- **Demo-ability:** Medium. It's hard to source a realistic AI-insertion example in the Finnish history dataset, but one can be simulated.

## 8. Link rot / dead references

- **What:** Cited URLs disappear, so claims become unverifiable.
- **Evidence:**
  - In a 50k-page sample, 53–54% of en-wiki pages have at least one broken reference link, and 11% of all reference links are inaccessible ([Pew Research, May 2024](https://www.pewresearch.org/data-labs/2024/05/17/when-online-content-disappears/markdown)).
  - InternetArchiveBot and the TARB effort have fixed more than 30 million broken links across hundreds of wikis ([Internet Archive blog, Apr 2026](https://blog.archive.org/2026/04/23/gone-but-not-forgotten-recovering-the-dead-web/)).
- **Who it hurts:** Readers and editors.
- **MariaDB angle:** A weak fit. This is largely solved by IABot. A small add-on: SVT stores the source snapshot text you embedded, so verification (#1) still works after the link dies.
- **Demo-ability:** Low. Not recommended as the main pitch.

## 9. Cross-language content gaps and staleness (secondary)

- **Gaps:** WMF treats content gaps across languages and topics as a core research area ([Redi et al., Knowledge Gaps taxonomy](https://arxiv.org/pdf/2008.12314)). The AI strategy proposes automated translation so smaller-language editors can focus on local context ([Nieman Lab](https://www.niemanlab.org/2025/04/wikipedia-announces-new-ai-strategy-to-support-human-editors/)). *Angle:* cross-lingual embeddings to find facts present in en but missing in fi (or the reverse) for the same history topic. *Demo-ability:* medium. It needs an en dataset, which isn't provided.
- **Staleness:** A newspaper audit of 1,000 random de-wiki articles found about 20% contained outdated information ([FAS via heise](https://heise.de/-10510852); **unverified**, secondary). *Angle:* SVT "last substantively edited" per section plus RAG detection of time-sensitive wording ("currently", "nykyään"). It matters less for history topics.

---

## Sources

- Baigutanova, Trokhymovych, …, Sáez Trumper (WMF). *Multilingual Reference Need Assessment System for Wikipedia*, 2026. https://arxiv.org/html/2603.17146v1
- Brooks, Eggert, Peskoff. *The Rise of AI-Generated Content in Wikipedia*, 2024. https://arxiv.org/html/2410.08044v1
- Flöck, Erdogan, Acosta. *TokTrack*, 2017. https://arxiv.org/abs/1703.08244
- Halfaker, Geiger, Morgan, Riedl. *The Rise and Decline of an Open Collaboration System*, 2013. https://meta.wikimedia.org/wiki/Research:The_Rise_and_Decline
- Petroni et al. *Improving Wikipedia Verifiability with AI* (SIDE), 2022/2023. https://arxiv.org/pdf/2207.06220
- Piccardi, Redi, Colavizza, West. *Quantifying Engagement with Citations on Wikipedia*, WWW 2020. https://arxiv.org/abs/2001.08614v1
- Piccardi & West. *Navigating Knowledge: Patterns and Insights from Wikipedia Consumption*, 2025. https://arxiv.org/pdf/2501.00939
- Redi, Fetahu, Morgan, Taraborelli. *Citation Needed*, WWW 2019. https://arxiv.org/pdf/1902.11116
- Redi, Gerlach, Johnson, Morgan, Zia. *A Taxonomy of Knowledge Gaps for Wikimedia Projects*. https://arxiv.org/pdf/2008.12314
- Singer et al. *Why We Read Wikipedia*, WWW 2017. https://arxiv.org/pdf/1702.05379
- Trokhymovych, Sen, Gerlach. *An Open Multilingual System for Scoring Readability of Wikipedia*, ACL 2024. https://arxiv.org/html/2406.01835v1
- Walden et al. *How Grounded is Wikipedia?*, 2025. https://arxiv.org/abs/2506.12637v1
- Yasseri, Spoerri, Graham, Kertész. *The Most Controversial Topics in Wikipedia*, 2014. https://arxiv.org/abs/1305.5566
- Wikimedia Foundation, Diff. *New User Trends on Wikipedia*, 17 Oct 2025. https://diff.wikimedia.org/2025/10/17/new-user-trends-on-wikipedia/
- Wikimedia Foundation. *Our new AI strategy puts Wikipedia's humans first*, 30 Apr 2025. https://wikimediafoundation.org/news/2025/04/30/our-new-ai-strategy-puts-wikipedias-humans-first/ (read via https://www.niemanlab.org/2025/04/wikipedia-announces-new-ai-strategy-to-support-human-editors/)
- Henner, C. *Special report*, Wikipedia Signpost, 15 Jan 2026 (opinion essay; uses stats.wikimedia.org). https://signpost.news/2026-01-15/Special_report
- Pew Research Center. *When Online Content Disappears*, 17 May 2024. https://www.pewresearch.org/data-labs/2024/05/17/when-online-content-disappears/markdown
- Pew Research Center. *Wikipedia at 25: What the data tells us*, 13 Jan 2026. https://www.pewresearch.org/short-reads/2026/01/13/wikipedia-at-25-what-the-data-tells-us/
- Internet Archive. *Gone but Not Forgotten*, 23 Apr 2026. https://blog.archive.org/2026/04/23/gone-but-not-forgotten-recovering-the-dead-web/
- Vapriikki / Tampere 1918. *The many names of the Finnish Civil War*. https://tampere1918.fi/en/war/the-many-names-of-the-finnish-civil-war/
- heise online. Report on Wikipedia speedy deletion for machine-generated content, 2025 (secondary). https://heise.de/-10510852
- Citation Hunt: https://meta.wikimedia.org/wiki/Citation_Hunt · fi-wiki categories (counts unverified): https://fi.wikipedia.org/wiki/Luokka:L%C3%A4hteett%C3%B6m%C3%A4t_artikkelit , https://fi.wikipedia.org/wiki/Wikipedia:Huomiota_kaipaavat_sivut
