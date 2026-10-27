# Project workflow

This flowchart connects U.S. policy announcements, news coverage, online discussion, and international-student mobility indicators. The study period is 2025–2026, with particular attention to Indian students. Events first enter a candidate list; each source, date, policy stage, and affected student or work pathway must be checked before an event is used in analysis.

```mermaid
flowchart TD
    A["Research question<br/>How do online discussions and stated study plans change around U.S. policy announcements affecting international students, especially Indian students?"]

    A --> B["Build and verify policy timeline<br/>Primary sources, announcement dates, policy stage, affected visas"]
    B --> C["Select student-relevant events<br/>Visa interviews and screening • travel and entry • student status • OPT/CPT and work pathways"]
    C --> D["Set collection window for each event<br/>Baseline → anticipation → immediate → extended"]

    D --> E["Collect news coverage<br/>News API / GDELT + education news outlets"]
    D --> F["Collect public discussions<br/>Reddit • YouTube comments • other accessible public sources"]
    D --> G["Collect context data<br/>Visa issuance • enrollment • other available mobility indicators"]

    E --> H["Create a structured dataset<br/>Text • date • source • URL/ID • policy event • collection window"]
    F --> H
    G --> I["Keep aggregate indicators separately<br/>Country • period • measure • source"]

    H --> J["Clean and screen records<br/>Remove duplicates and irrelevant content;<br/>separate news, student accounts, advice, and general opinion"]
    J --> K["Code a reviewed sample by hand<br/>Define categories and check whether the labels are consistent"]

    K --> L["Classify the full discussion dataset"]
    L --> M["Policy issue<br/>Visa process • travel • legal status • work options • safety • cost"]
    L --> N["Type of discussion<br/>Question • personal experience • advice • reaction"]
    L --> O["Stated study plan, when present<br/>Continue • delay • withdraw • consider another country • unclear"]
    L --> P["Expressed concern or sentiment<br/>For example: uncertainty, fear, optimism, frustration"]

    M --> Q["Analyze patterns by policy event and time window"]
    N --> Q
    O --> Q
    P --> Q
    E --> R["Analyze how news framed each event"]
    R --> Q
    I --> S["Compare discussion patterns with later aggregate indicators"]
    Q --> S

    S --> T["Project outputs<br/>Source-verified policy timeline • source and category breakdown<br/>discussion trends • stated-plan trends • carefully qualified conclusions"]
```

**Classification rule:** A post expressing worry about a visa is coded as a concern, but it is not coded as a decision to delay or withdraw unless the writer explicitly states that plan. News coverage, student experiences, and general public comments remain identifiable as separate source types.

**Policy verification gate:** The event collector and its LLM produce candidates, not verified policy facts. Check the primary source for the announcement date, whether the item is proposed or final, affected visa classes, and direct relevance to international students. Check any earlier news signal against the linked article before using it to set an anticipation window. Keep the event source URL and verification notes with the timeline. The analysis windows end at the fixed study stop date, October 1, 2026.
