"""Local company knowledge base (static documentation for the agent).

This is company-provided information, not customer memory:

    Knowledge Base = documentation we ship
    Hindsight      = what we learned about a specific customer
    MySQL          = structured application state
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    title: str
    category: str
    tags: tuple[str, ...]
    content: str


def _doc(doc_id: str, title: str, category: str, tags: str, content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=doc_id,
        title=title,
        category=category,
        tags=tuple(tag.strip() for tag in tags.split(",") if tag.strip()),
        content=content.strip(),
    )


DOCUMENTS: Sequence[KnowledgeDocument] = (
    _doc(
        "kb-api-auth",
        "API Authentication Guide",
        "api",
        "auth,api,token,key,401,oauth",
        """
Scope: API authentication for all RecallDesk platform endpoints.

1. Every request must send `Authorization: Bearer <access_token>`.
2. Access tokens are short lived. Refresh them through the token endpoint.
3. A 401 means the token is missing, expired or malformed. Refresh and retry once.
4. A 403 means the token is valid but the principal lacks the required role.
5. Never place API keys in client-side code or in a URL query string.
6. Rotate credentials immediately if they appear in a log or public repository.

Troubleshooting: if a request returns 401 from every environment, verify the
system clock skew of the calling service before rotating anything.
        """,
    ),
    _doc(
        "kb-database-troubleshooting",
        "Database Troubleshooting",
        "database",
        "postgres,mysql,connection,pool,timeout,rds,timeout,query,slow",
        """
Scope: diagnosing database connectivity and performance.

1. Connection pool exhaustion is the most common cause of API timeouts.
   Symptom: "too many clients already", connection timeouts, latency spikes
   under load. Fix: raise the pool limit, add a pooler, and return connections
   to the pool on every code path (including error paths).
2. Long running transactions block vacuum and hold locks. Keep transactions
   short and never hold one open while calling an external service.
3. Check slow query logs before adding indexes. Add an index only after you
   can name the query it serves.
4. On managed PostgreSQL (RDS), confirm the instance is not CPU throttled
   before assuming the application is at fault.
5. Confirm TLS settings match the server requirement before debugging auth.
6. After any pool change, verify with a load test, not a single request.
        """,
    ),
    _doc(
        "kb-deployment-runbook",
        "Deployment Runbook",
        "deployment",
        "deploy,release,rollback,ci,cd,build,production",
        """
Scope: shipping and rolling back a production release.

1. Deployments are forward-only through CI. Never hot-fix a running container.
2. Every release must be backward compatible with the previous version for at
   least one deploy window (expand/contract schema changes).
3. Rollback procedure: stop the rollout, revert to the previous image tag,
   confirm health checks pass, then re-verify the affected endpoints.
4. Database migrations run before the new application version is enabled.
5. Feature flags are preferred for risky behaviour changes.
6. Record the release tag, the commit, and the operator in the change log.
        """,
    ),
    _doc(
        "kb-rate-limit-policy",
        "Rate Limit Policy",
        "limits",
        "rate,limit,429,quota,throttle,burst",
        """
Scope: API rate limits and quotas.

1. Default limit: 600 requests per minute per API key, burst 100.
2. Limits are enforced per key, not per end user.
3. A 429 response includes `Retry-After` in seconds. Honour it.
4. Exceeding a limit repeatedly for 24 hours downgrades the key to a lower tier.
5. Approved limit increases require a ticket with the expected peak request
   rate and the business justification.
6. Do not implement client-side retry loops that retry faster than Retry-After.
        """,
    ),
    _doc(
        "kb-billing-faq",
        "Billing FAQ",
        "billing",
        "invoice,plan,usage,refund,charge,subscription,seats",
        """
Scope: how customers are charged.

1. Plans are billed monthly in advance on the first of the month.
2. Seats are counted from the number of active users on the last day of the
   billing period.
3. Usage above the plan allowance is billed as overage at the end of the period.
4. Refunds are issued for full months only, within 30 days of the charge.
5. Changing plan takes effect at the next renewal, never mid-cycle.
6. Billing questions do not require engineering escalation unless the invoice
   is mathematically wrong.
        """,
    ),
    _doc(
        "kb-incident-response",
        "Incident Response Guide",
        "incident",
        "incident,outage,severity,sev,oncall,postmortem,escalation",
        """
Scope: handling a production incident.

1. Severity 1 = customer facing outage, no workaround. Page the on-call lead
   immediately and post status updates every 30 minutes.
2. Severity 2 = major degradation or partial outage. Engage within 30 minutes.
3. Severity 3 = minor or internal impact. Handle during business hours.
4. Mitigate first, diagnose second. Restore service, then find the cause.
5. Customer facing incidents require a written postmortem within five business
   days, blameless and action tracked.
6. Escalate when the blast radius is unknown, data integrity is at risk, or
   the mitigation requires a risky change.
        """,
    ),
)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "to", "and", "in", "on", "for", "with",
    "we", "it", "this", "that", "was", "were", "be", "by", "at",
}


def _tokens(text: str) -> List[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


class KnowledgeBaseService:
    def __init__(self, documents: Sequence[KnowledgeDocument] = DOCUMENTS) -> None:
        self._documents: List[KnowledgeDocument] = list(documents)
        self._index: Dict[str, Dict[str, float]] = {
            doc.id: self._index_document(doc) for doc in self._documents
        }

    @staticmethod
    def _index_document(doc: KnowledgeDocument) -> Dict[str, float]:
        """Weighted token index: title/tags/category matter more than body text."""
        index: Dict[str, float] = {}

        def add(tokens: List[str], weight: float) -> None:
            for token in tokens:
                index[token] = index.get(token, 0.0) + weight

        add(_tokens(doc.title), 4.0)
        add(_tokens(" ".join(doc.tags)), 2.5)
        add(_tokens(doc.category), 2.0)
        add(_tokens(doc.content), 1.0)
        return index

    @property
    def documents(self) -> List[KnowledgeDocument]:
        return list(self._documents)

    def list_documents(self) -> List[Dict[str, object]]:
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "category": doc.category,
                "tags": list(doc.tags),
            }
            for doc in self._documents
        ]

    def get(self, document_id: str) -> KnowledgeDocument | None:
        for doc in self._documents:
            if doc.id == document_id:
                return doc
        return None

    def search(self, query: str, limit: int = 3) -> List[Dict[str, object]]:
        query_tokens = set(_tokens(query))
        if not query_tokens:
            return []
        scored: List[tuple[float, KnowledgeDocument]] = []
        for doc in self._documents:
            index = self._index[doc.id]
            matched = [token for token in query_tokens if index.get(token)]
            if not matched:
                continue
            weight = sum(index[token] for token in matched)
            coverage = len(matched) / len(query_tokens)
            score = weight * coverage
            if doc.category.lower() in query.lower():
                score *= 1.5
            scored.append((score, doc))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        results = []
        for score, doc in scored[:limit]:
            results.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "category": doc.category,
                    "tags": list(doc.tags),
                    "content": doc.content.strip(),
                    "relevance": round(min(score / 8.0, 1.0), 4),
                }
            )
        return results


knowledge_base = KnowledgeBaseService()
