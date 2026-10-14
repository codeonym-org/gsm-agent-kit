# Domain docs

This monorepo uses a single domain-documentation context.

## Before exploring

Read GLOSSARY.md at the repository root and relevant decisions in docs/adr/.

If these files do not exist, proceed silently. The domain-modeling skill
creates them as terminology and decisions are resolved.

## Layout

- GLOSSARY.md: shared domain vocabulary.
- docs/adr/: numbered architecture decision records.

Package boundaries do not automatically define separate domain contexts.

## Consumer rules

Use glossary terms consistently in issues, proposals, code and tests.
When a needed term is missing, reconsider the terminology or note the gap
for domain modeling.

If a proposal contradicts an ADR, name the ADR and explain why the
decision should be revisited.
