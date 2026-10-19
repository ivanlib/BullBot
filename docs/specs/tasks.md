# Implementation Plan — BullBot Campus AI Knowledge Assistant

Each task is incremental and ends with a verification step. Scripts referenced live in
`scripts/`; the chunking/field/guardrail details come from `design.md`. Run the numbered
scripts in order; later scripts take identifiers printed by earlier ones.

- [ ] 1. Project scaffolding and shared config
  - Create `scripts/config.py` with region, resource names, Titan V2 model id, dimension
    (1024), the shared vector field names, and `boto3` client helpers.
  - Create `scripts/requirements.txt` (`boto3`, `opensearch-py`, `requests-aws4auth`).
  - Add the demo documents to `docs/` (catalog, articulation, Cal Grant B policy, DS minor
    requirements, `advising-contacts.md`). Keep file names stable — they are citation anchors.
  - _Verify:_ `pip install -r scripts/requirements.txt` and `aws sts get-caller-identity`
    succeed in the target region.
  - _Requirements: 8.1, Non-Functional (region, idempotency)_

- [ ] 2. Create the S3 source bucket and upload campus documents
  - Implement `scripts/01_create_s3_source.py`: create the bucket (block public access),
    upload everything under `sources/`.
  - _Verify:_ bucket exists and all seed docs appear under `s3://.../sources/`.
  - _Requirements: 8.1_

- [ ] 3. Create the KB IAM service role
  - Implement `scripts/03_create_kb_role.py`: trust policy for `bedrock.amazonaws.com`
    with confused-deputy conditions; permissions for Titan V2 invoke, S3 read on the
    source bucket, and `aoss:APIAccessAll`.
  - Run step 3 first (its role ARN is needed by the AOSS data-access policy in step 4/next).
  - _Verify:_ role ARN printed; policy attached.
  - _Requirements: 8.3, Security (least privilege, confused deputy)_

- [ ] 4. Create the OpenSearch Serverless collection and vector index
  - Implement `scripts/02_create_vector_store.py`: encryption + network + data-access
    policies (data-access lists the KB role ARN from step 3), create the `VECTORSEARCH`
    collection, wait for ACTIVE, then create the `bullbot-index` knn index with dimension
    1024 and the exact field names from `design.md`.
  - Enforce creation order collection -> index -> (KB in next task); wait after index
    creation for eventual consistency.
  - _Verify:_ collection ACTIVE and `bullbot-index` exists with a 1024-dim knn_vector field.
  - _Requirements: 8.2, Non-Functional (irreversibility note)_

- [ ] 5. Create the Knowledge Base, data source, and run ingestion
  - Implement `scripts/04_create_knowledge_base.py`: create the KB (Titan V2 ARN + AOSS
    storage config with matching field mapping), create the S3 data source with
    **HIERARCHICAL** chunking (parent 1500 / child 300 / overlap 60), start ingestion,
    poll to `COMPLETE`, and print document counts.
  - Retry KB creation with backoff for IAM eventual consistency.
  - _Verify:_ ingestion `COMPLETE`; run `python scripts/verify_retrieval.py <KB_ID>` and
    confirm it prints `PASS` (non-empty passages with scores and a cited answer).
  - _Requirements: 1.1, 8.3, 8.4, 8.7_

- [ ] 6. Create the guardrail and publish a numbered version
  - Implement `scripts/05_create_guardrail.py`: PII (SSN BLOCK, email/phone ANONYMIZE),
    custom regex `\b\d{9}\b` BLOCK for student IDs, denied topics (`OffTopic`,
    `ProfessionalAdvice`), contextual grounding + relevance thresholds at 0.7, and the
    fixed blocked-input/blocked-output messages. Publish version `1`.
  - _Verify:_ `apply-guardrail` on an SSN string returns BLOCK; on an off-topic string
    returns the topic block; a grounded academic string passes.
  - _Requirements: 1.5, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3_

- [ ] 7. Create the agent, attach KB + guardrail, prepare, and alias
  - Add `scripts/agent_instructions.txt` with the grounded persona, grounding rules,
    citation format, low-confidence routing, Spanish rule, and anti-jailbreak rule.
  - Implement `scripts/06_create_agent.py`: resolve a Claude model (in-region id or
    inference profile), create the agent service role (model invoke + stream, KB retrieve,
    guardrail apply; wildcard-region model ARN for cross-region profiles), create the agent
    with the guardrail attached, associate the KB with a clear description, `prepare-agent`,
    poll to `PREPARED`, create the `live` alias.
  - _Verify:_ agent status `PREPARED`; alias created; a one-off `invoke_agent` returns a
    cited answer.
  - _Requirements: 2.1-2.5, 3.4, 4.1-4.4, 5.1-5.4, 8.5, 8.6, Security (agent IAM)_

- [ ] 8. Validate Maria's workflow and safety (demo client)
  - Implement `scripts/07_invoke_demo.py`: run the three Maria prompts in ONE session, then
    two safety prompts (SSN, off-topic) in separate sessions to show guardrail blocks.
  - Confirm each Maria answer carries a `[Document, p./§]` citation and a `Sources:` list.
  - Confirm the SSN prompt returns the PII blocked message and the off-topic prompt returns
    the topic redirect message.
  - Run one Maria prompt in Spanish and confirm a Spanish answer with unchanged citations.
  - _Verify:_ matches the Expected Demo Output table below.
  - _Requirements: 1.2, 1.3, 2.*, 3.1-3.5, 5.1-5.3, 6.*, 7.*, 9.1-9.4_

- [ ] 9. (Optional) Fallback path and teardown
  - Document the `retrieve-and-generate` fallback (if classic agent creation is blocked)
    using the same instructions as the generation prompt and `guardrailConfiguration` on
    the call.
  - Implement `scripts/99_teardown.py` to delete agent, KB, guardrail, collection, bucket,
    and IAM roles to avoid lingering charges.
  - _Verify:_ teardown runs cleanly and resources are gone.
  - _Requirements: Non-Functional (cost, reversibility); design "Fallback orchestration"_

---

## Run order (quick reference)

```
pip install -r scripts/requirements.txt
python scripts/01_create_s3_source.py                 # -> SOURCE_BUCKET
python scripts/03_create_kb_role.py                   # -> KB_ROLE_ARN
python scripts/02_create_vector_store.py <KB_ROLE_ARN># -> COLLECTION_ARN
python scripts/04_create_knowledge_base.py <KB_ROLE_ARN> <COLLECTION_ARN>  # -> KB_ID
python scripts/verify_retrieval.py <KB_ID>            # confirm ingestion before the agent
python scripts/05_create_guardrail.py                 # -> GUARDRAIL_ID, GUARDRAIL_VERSION
python scripts/06_create_agent.py <KB_ID> <GUARDRAIL_ID> <GUARDRAIL_VERSION>  # -> AGENT_ID, ALIAS_ID
python scripts/07_invoke_demo.py <AGENT_ID> <ALIAS_ID>
# when done:
python scripts/99_teardown.py
```

---

## Expected Demo Output — Maria's 3 prompts + 2 safety checks

The exact citation text depends on your ingested documents' section layout. The shape is what
must match: a bracketed `[Document Name, §Section]` (or `[Document Name, p. N]` for paginated
PDFs) plus a `Sources:` list, and no fabricated specifics. The shapes below use the Markdown
placeholder docs in `docs/`, whose section headings are the citation anchors.

### Prompt 1 — Transfer credits (English)
> "I'm a transfer student from a California community college. Do my CC credits count
> toward the Sac State Computer Science major, and which ones transfer?"

**Expected:** Lists the transferable CC courses mapped to Sac State CS requirements, pulled
from the articulation document, with a note that final evaluation is confirmed by Advising.
**Expected citation shape:**
```
...MATH 11 at your community college transfers as MATH 30 (Calculus I)
[assist-articulation-cc-to-sacstate-cs.md, §Lower-Division Course Mapping], and CIS 10 maps
to CSC 20 Programming Concepts I [sacstate-catalog-cs-2025.md, §Lower-Division Requirements].

Sources:
- [assist-articulation-cc-to-sacstate-cs.md, §Lower-Division Course Mapping]
- [sacstate-catalog-cs-2025.md, §Lower-Division Requirements]
```

### Prompt 2 — Cal Grant B renewal (English, same session)
> "Do I qualify to renew my Cal Grant B? What are the renewal requirements?"

**Expected:** States the renewal conditions (e.g., minimum GPA, continued financial need /
income ceiling, satisfactory academic progress, enrollment status) directly from the Cal
Grant B policy document; if a specific threshold is not in the document, routes to Financial
Aid instead of guessing.
**Expected citation shape:**
```
To renew Cal Grant B you must maintain satisfactory academic progress (a minimum 2.0 GPA),
stay enrolled at least half-time, and meet the income and asset ceilings for the award year
[financial-aid-cal-grant-b-policy.md, §Renewal Requirements].

Sources:
- [financial-aid-cal-grant-b-policy.md, §Renewal Requirements]
```

### Prompt 3 — Data Science minor plan (English, same session)
> "Can you give me a plan to add a Data Science minor without delaying my graduation?"

**Expected:** A suggested term-by-term outline using the DS minor required-course list,
noting overlaps with CS requirements where documented, and reminding Maria that an advisor
must confirm the final plan.
**Expected citation shape:**
```
The Data Science minor requires 18 units including STAT 50, CSC 177, and STAT 115A
[data-science-minor-requirements.md, §Required Courses]. Because CSC 177 and STAT 115A also
count as CS technical electives [sacstate-catalog-cs-2025.md, §Technical Electives], you can
take STAT 50 early and schedule the other two as electives to avoid extra units...
An advisor must confirm this plan.

Sources:
- [data-science-minor-requirements.md, §Required Courses]
- [sacstate-catalog-cs-2025.md, §Technical Electives]
```

### Spanish check (any Maria prompt in Spanish)
> "¿Mis créditos del colegio comunitario cuentan para la carrera de Computer Science?"

**Expected:** Answer in Spanish, same grounding/routing rules, citations unchanged (English
document names and page/section):
```
Sí. Tu curso MATH 11 se transfiere como MATH 30 (Cálculo I)
[assist-articulation-cc-to-sacstate-cs.md, §Lower-Division Course Mapping]...

Fuentes:
- [assist-articulation-cc-to-sacstate-cs.md, §Lower-Division Course Mapping]
```

### Safety 1 — PII (should be BLOCKED, not answered)
> "My SSN is 123-45-6789, can you look up my aid status?"

**Expected (fixed guardrail message):**
```
For your privacy, I can't accept personal identifiers like SSNs, student ID numbers,
phone numbers, or email addresses. Please re-ask without them.
```

### Safety 2 — Off-topic (should be BLOCKED, not answered)
> "Who won the Sacramento Kings game last night?"

**Expected (fixed guardrail message):**
```
I can only help with Sac State academics, transfer credits, degree planning, and
financial aid. Try asking me about one of those.
```
