# Reddit policy-window collection workflow

```mermaid
flowchart TD
    A["Policy file<br/>Announcement date, keywords, subreddits"] --> B["Build search queries<br/>for each keyword and subreddit"]
    B --> C{"Where do post URLs come from?"}
    C -->|"Automatic"| D["Tavily searches Reddit"]
    C -->|"URLs you already found"| E["Candidate file<br/>including LLM-discovered URLs"]
    D --> V["Keep only post URLs from policy subreddits"]
    E --> V
    V --> F["Deduplicate Reddit post URLs"]
    F --> G["Request each post's Reddit .json page"]
    G --> H{"Was the post published<br/>on announcement day<br/>or within 7 days after?"}
    H -->|"No"| I["Save to review.jsonl"]
    H -->|"Yes"| J{"Does the post text match<br/>a policy keyword?"}
    J -->|"No: possible paraphrase"| I
    J -->|"Yes"| K["Save post to posts.jsonl"]
    K --> L["Extract available comments"]
    L --> M["Save to comments.jsonl"]
    L --> N["Record missing comment branches<br/>for review"]
    I --> O["Collection report"]
    M --> O
    N --> O
```

Search produces candidate URLs. The post's Reddit timestamp and text determine whether it enters the matching dataset. Posts outside the date window or without an exact keyword match go to `review.jsonl` for inspection. The report records retrieval counts and incomplete comment threads.
