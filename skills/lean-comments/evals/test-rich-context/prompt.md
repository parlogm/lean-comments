---
tags: [skill-creator]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Write a JUnit 5 + AssertJ test class PriceListCacheTest in src/test/java (same package) for PriceListCache. Background: our integration tests run with cache.enabled=false, so nothing currently proves that find() caches and evict() clears the same entry. We had a prod incident (INC-311) where evict built the key with a different prefix than find, so stale price lists were served for 24h until the TTL expired. Cover: a second find for the same store does not call the loader again; evict then find calls the loader again; evicting one store leaves another store cached.

Input files: src/main/java/com/example/catalog/pricing/PriceListCache.java
