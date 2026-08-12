# Prohibited-scope audit

Date: 2026-08-10  
Feature: `001-nutrition-recipe-planner`  
Result: **PASS**

## Method

The audit inspected all 45 declared OpenAPI operations, the 14 React route declarations (including
layout, redirects, and fallbacks), direct Python and Node dependencies, MCP tools/resources, and the
product and operator documentation. Generated build output, installed packages, and test-result
folders were excluded from source searches.

Commands used from the repository root:

```powershell
rg -n -i "chatbot|chat bot|photo recognition|image recognition|computer vision|social feed|follow user|subscription|medical advice|diagnos|multi[- ]user|team workspace|organization|tenant" backend frontend docs deploy README.md specs/001-nutrition-recipe-planner --glob '!**/node_modules/**' --glob '!**/dist/**' --glob '!**/test-results/**'
rg -n -i "openai|anthropic|langchain|transformers|opencv|tensorflow|torch|stripe|auth0|clerk|social|chat" backend/pyproject.toml backend/uv.lock frontend/package.json frontend/pnpm-lock.yaml
rg -n "APIRouter|router\\.(get|post|put|patch|delete)" backend/src/cookfully/api/routes
rg -n "<Route " frontend/src/app/App.tsx
rg -n '^\\s+operationId:' specs/001-nutrition-recipe-planner/contracts/openapi.yaml
```

The dependency search returned zero prohibited direct Python dependencies and zero prohibited direct
Node dependencies. Lockfile matches were reviewed as transitive package metadata rather than treated
as product features.

## Findings

| Prohibited or constrained scope | Evidence reviewed | Conclusion |
| --- | --- | --- |
| In-app chatbot or open-ended assistant | React routes/components, API operations, MCP server | No chat UI, conversation model, or chat endpoint exists. Goal-aware suggestions are form-driven deterministic optimization. MCP is an authenticated external integration surface, not an in-app chatbot. |
| Photo nutrition recognition | Media route/model, recipe import pipeline, dependencies | Recipe images are stored and served only. There is no upload-to-recognition workflow, vision model, OCR, classifier, or nutrition-from-photo API. |
| Social/community features | UI routes, API operations, identity models, dependencies | No profiles, following, feeds, comments, sharing graph, invites, or community routes exist. |
| Subscription-only core | Manifests, configuration, provider-degraded tests and docs | Core manual recipe, nutrition, planning, grocery, backup, and export workflows are local and self-hosted. No billing SDK is present. The optional structured provider is not required for core operation. |
| Medical-advice presentation | Recipe, plan, suggestion, OpenAPI, MCP, export, and methodology surfaces | Nutrition is consistently framed as an estimate/planning aid rather than diagnosis or treatment. Recipe nutrition, micronutrient totals, suggestions, API/MCP descriptions, exports, and methodology carry the limitation. No clinical recommendation or prescription route exists. |
| Unapproved broad multi-user scope | Authentication, owner preferences, authorization, routes, data model | The implementation has one bootstrapped owner and scoped access tokens. It has no tenant, organization, membership, role-administration, invite, or broad multi-user management surface. The approved “one owner or small household” operating assumption does not introduce separate user identities or administration. |

## Boundary judgments

- “Agent access” is intentionally retained: it creates revocable scoped tokens for the documented
  API/MCP operations. It does not add conversational UI or autonomous medical guidance.
- Goal-aware suggestions are intentionally retained: their inputs, constraints, deterministic ranking,
  preview, and acceptance are explicit. They do not use open-ended conversation.
- Recipe image storage is intentionally retained: passive media handling is not photo recognition.
- References to Mealie, Tandoor Recipes, and Immich in `docs/inspiration-review.md` are comparative
  design research, not imported product scope. Each comparison records domain differences and avoids
  treating any inspiration implementation as automatically correct.

No prohibited route, UI surface, direct dependency, or affirmative documentation promise was found.
Any future chatbot, recognition, social/community, billing-required, clinical, or broad multi-user
capability requires a separately approved specification and a repeat of this audit.
