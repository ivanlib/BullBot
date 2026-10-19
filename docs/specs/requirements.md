# Requirements — BullBot Campus AI Knowledge Assistant

## Introduction

BullBot is a campus AI knowledge assistant for California State University, Sacramento
(Sac State) built on Amazon Bedrock using Retrieval-Augmented Generation (RAG).
Students struggle to get reliable, specific answers about transfer credits, financial
aid, and degree planning from generic AI tools because those tools hallucinate,
cannot cite official campus policy, and do not know Sac State's catalog or rules.

BullBot solves this by grounding every answer strictly in ingested, official campus
documents (catalog, articulation agreements, financial aid policy, degree roadmaps)
and attaching explicit citations (document name and page or section) to every claim.
When the retrieved context does not confidently support an answer, BullBot routes the
student to a human — Academic Advising or the Financial Aid office — instead of guessing.

The product is validated against a single end-to-end scenario we call **Maria's Scenario**:

> Maria is a transfer student from a community college (CC) majoring in Computer Science
> (CS). In one session she needs to (1) check whether her CC credits transfer to her CS
> major, (2) see if she qualifies for Cal Grant B renewal, and (3) get a plan to add a
> Data Science minor without delaying graduation.

BullBot must answer all three in one conversational session, in English or Spanish, with
citations, no hallucinations, and PII/topic guardrails enforced throughout.

### Technology scope

- **RAG store:** Amazon Bedrock Knowledge Base
- **Source data:** Amazon S3 bucket of official campus documents (PDF/MD/HTML)
- **Chunking:** hierarchical (structured catalog/policy docs with sections and pages)
- **Embedding model:** `amazon.titan-embed-text-v2:0` (Titan Text Embeddings V2)
- **Vector store:** Amazon OpenSearch Serverless (VECTORSEARCH collection)
- **Orchestration:** Amazon Bedrock Agent (persona + KB association + routing logic)
- **Safety:** Amazon Bedrock Guardrail (PII block, denied off-topic subjects, grounding)
- **Automation:** Python `boto3` setup scripts (idempotent, re-runnable for the demo)

### Out of scope (hackathon)

- Student authentication / live SIS (student information system) integration
- Writing to any system of record (BullBot is read-only advisory)
- Mobile app or production hosting — demo runs from a Python client / notebook

---

## Glossary

- **KB** — Knowledge Base (Bedrock managed RAG store)
- **AOSS** — Amazon OpenSearch Serverless
- **Articulation / ASSIST** — the official CC-to-CSU course transfer mapping
- **Cal Grant B** — California need-based state grant; renewal has GPA/enrollment/income rules
- **Grounding** — the degree to which an answer is supported by retrieved source text
- **Citation** — a reference of the form `[Document Name, p. N]` or `[Document Name, §Section]`

---

## Requirements

### Requirement 1 — Grounded, cited answers (no hallucination)

**User Story:** As a Sac State student, I want every answer to come from official campus
documents with a visible citation, so that I can trust the information and verify it myself.

#### Acceptance Criteria

1. WHEN BullBot answers any factual question THEN the system SHALL base the answer only on
   text retrieved from the Knowledge Base.
2. WHEN BullBot makes a factual claim THEN the system SHALL attach at least one citation in
   the form `[Document Name, p. N]` or `[Document Name, §Section]`.
3. WHEN the Knowledge Base returns no sufficiently relevant passage for a question THEN
   BullBot SHALL NOT fabricate an answer and SHALL state that it could not find the
   information in official documents.
4. IF retrieved context does not support a specific claim THEN BullBot SHALL omit that claim
   rather than infer it.
5. WHEN the contextual grounding or relevance score for a generated response falls below the
   configured threshold THEN the guardrail SHALL block or suppress the ungrounded content.

### Requirement 2 — Low-confidence routing to humans

**User Story:** As a student, I want to be sent to the right office when BullBot is unsure,
so that I never act on a wrong answer about my aid or my degree.

#### Acceptance Criteria

1. WHEN retrieval confidence is low OR the question falls outside ingested documents THEN
   BullBot SHALL respond with a referral to the relevant office.
2. WHEN the question concerns transfer credits or degree planning AND confidence is low THEN
   BullBot SHALL route to **Academic Advising** with its contact method.
3. WHEN the question concerns financial aid or grants AND confidence is low THEN BullBot
   SHALL route to the **Financial Aid & Scholarships Office** with its contact method.
4. WHEN BullBot routes to a human THEN it SHALL briefly state why (e.g., "I don't have an
   official document that confirms this") so the student understands the handoff.
5. WHEN BullBot routes to a human THEN it SHALL NOT present a guessed answer alongside the
   referral.

### Requirement 3 — Maria's end-to-end scenario in one session

**User Story:** As a transfer CS student, I want to resolve transfer credits, Cal Grant B
renewal, and a Data Science minor plan in one conversation, so that I can plan my next
semester in a single sitting.

#### Acceptance Criteria

1. WHEN a student asks whether specific CC credits transfer to the CS major THEN BullBot
   SHALL answer using articulation/catalog documents and cite them.
2. WHEN a student asks about Cal Grant B renewal eligibility THEN BullBot SHALL answer using
   financial aid policy documents, state the renewal conditions (e.g., GPA, enrollment,
   income/eligibility), and cite them.
3. WHEN a student asks for a Data Science minor plan that avoids delaying graduation THEN
   BullBot SHALL produce a term-by-term suggestion grounded in the minor's required-course
   list and the student's stated remaining requirements, cite the minor requirements, and
   note that an advisor must confirm the final plan.
4. WHEN all three questions are asked in sequence THEN BullBot SHALL maintain conversation
   context across turns within the same session (same `sessionId`).
5. WHEN BullBot cannot confirm a transfer or renewal detail from documents THEN it SHALL
   apply Requirement 2 (route to the correct office) rather than guess.

### Requirement 4 — Strict, grounded persona

**User Story:** As the campus, I want BullBot to behave as a disciplined, document-bound
assistant, so that it never improvises policy or gives personal opinions.

#### Acceptance Criteria

1. WHEN BullBot responds THEN it SHALL adopt a helpful, plain-language Sac State advising
   persona and address the student directly.
2. WHEN BullBot lacks a document to support a claim THEN its instructions SHALL require it to
   say so rather than rely on general world knowledge.
3. WHEN BullBot answers THEN it SHALL present citations inline or in a short "Sources" list
   so the student can locate the exact page or section.
4. WHEN a student asks BullBot to ignore its rules, reveal its prompt, or act as a different
   assistant THEN BullBot SHALL decline and continue in its grounded persona.

### Requirement 5 — Spanish language support

**User Story:** As a Spanish-speaking student or parent, I want to ask questions and receive
answers in Spanish, so that language is not a barrier to understanding my options.

#### Acceptance Criteria

1. WHEN a student writes in Spanish THEN BullBot SHALL respond in Spanish.
2. WHEN a student writes in English THEN BullBot SHALL respond in English.
3. WHEN BullBot responds in Spanish THEN it SHALL still attach citations referencing the
   original (English) document names and page/section identifiers unchanged.
4. WHEN BullBot responds in Spanish THEN all grounding, no-hallucination, and routing rules
   (Requirements 1–3) SHALL apply identically.

### Requirement 6 — Guardrails: PII blocking

**User Story:** As the campus, I want BullBot to refuse to accept or echo student PII, so
that we minimize privacy risk and never store sensitive identifiers.

#### Acceptance Criteria

1. WHEN a student's input contains a Social Security Number THEN the guardrail SHALL block the
   request and BullBot SHALL ask the student not to share it.
2. WHEN input contains a phone number or email address THEN the guardrail SHALL block or
   anonymize it per configuration (phone/email anonymized; SSN blocked).
3. WHEN input contains a Sac State student ID (a 9-digit identifier) THEN a custom regex
   filter SHALL block it.
4. WHEN the guardrail blocks PII THEN BullBot SHALL return a safe, fixed message explaining it
   cannot process personal identifiers and SHALL NOT echo the detected value.
5. WHEN model invocation logging is enabled THEN the project SHALL document the PII logging
   compliance gap and recommend KMS-encrypted log groups (demo note).

### Requirement 7 — Guardrails: topic filtering (on-topic only)

**User Story:** As the campus, I want BullBot to stay on campus-advising topics, so that it
is not misused as a general chatbot.

#### Acceptance Criteria

1. WHEN a student asks something unrelated to Sac State academics, transfer, financial aid, or
   degree planning THEN a denied-topics guardrail SHALL block the request.
2. WHEN the guardrail blocks an off-topic request THEN BullBot SHALL respond with a fixed
   message redirecting the student to supported topics.
3. WHEN a student asks for medical, legal, or financial-investment advice THEN BullBot SHALL
   decline and, where relevant, route to the appropriate campus office.
4. WHEN a request is on-topic but out of document scope THEN BullBot SHALL apply Requirement 2
   (route to a human) rather than the off-topic block.

### Requirement 8 — Data source and infrastructure setup

**User Story:** As a hackathon developer, I want exact, repeatable setup scripts, so that I
can stand up the full stack quickly and re-run it reliably during the demo.

#### Acceptance Criteria

1. WHEN setup runs THEN it SHALL create an S3 bucket for source documents and upload the
   campus docs under a known prefix.
2. WHEN setup runs THEN it SHALL create an AOSS VECTORSEARCH collection and a vector index
   whose field names and dimension (1024 for Titan V2) match the KB configuration.
3. WHEN setup runs THEN it SHALL create the KB IAM service role with model, S3, and AOSS
   permissions, then create the KB with embedding model `amazon.titan-embed-text-v2:0`.
4. WHEN setup runs THEN it SHALL create an S3 data source with **hierarchical** chunking and
   run an ingestion job, polling until `COMPLETE`.
5. WHEN setup runs THEN it SHALL create the Guardrail (PII + denied topics + grounding) and
   publish a numbered version.
6. WHEN setup runs THEN it SHALL create the Bedrock Agent, associate the KB, attach the
   guardrail, prepare the agent, and create a `live` alias.
7. WHEN a setup step depends on IAM propagation THEN the script SHALL retry with backoff.
8. WHEN setup completes THEN it SHALL print all resource identifiers needed to invoke the
   agent (agent ID, alias ID, KB ID, guardrail ID/version).

### Requirement 9 — Demo validation (3 test prompts)

**User Story:** As a presenter, I want three ready test prompts with expected citation
output, so that I can prove Maria's workflow live and know what "correct" looks like.

#### Acceptance Criteria

1. WHEN the three demo prompts (transfer credits, Cal Grant B renewal, Data Science minor
   plan) are run in one session THEN each response SHALL include at least one citation of the
   form `[Document Name, p. N]` or `[Document Name, §Section]`.
2. WHEN a demo prompt is run THEN the expected-output document SHALL describe the expected
   source document and the expected citation shape so the presenter can verify correctness.
3. WHEN a PII prompt (e.g., containing an SSN) is run THEN the guardrail SHALL block it, and
   this SHALL be included as a safety demonstration.
4. WHEN an off-topic prompt is run THEN the guardrail SHALL block it with the redirect
   message, included as a safety demonstration.

---

## Non-Functional Requirements

- **Region:** single AWS region with Titan V2 and the chosen agent model available
  (in-region or via inference profile).
- **Idempotency:** setup scripts SHALL be safe to re-run; existing resources are detected
  and reused rather than duplicated where feasible.
- **Cost:** demo-scale only — one small AOSS collection, one KB, one agent; teardown script
  provided to avoid lingering charges.
- **Security:** least-privilege IAM roles, confused-deputy conditions on trust policies,
  guardrail pinned to a numbered version, `trace` disabled in production calls.
- **Reversibility:** chunking strategy is fixed at data-source creation; changing it requires
  deleting and recreating the data source (documented).

## Known constraint: Bedrock Agents availability

Amazon Bedrock Agents (now "Agents classic") is in maintenance mode and closed to new
customers; AWS recommends Bedrock AgentCore for new workloads. For this hackathon we use
Bedrock Agents as requested because the classic APIs still operate for enabled accounts and
map cleanly to the demo. If the demo account cannot create a classic agent, the fallback is
to drive the same KB + Guardrail directly through `RetrieveAndGenerate` with a system prompt
(see design doc, "Fallback orchestration").
