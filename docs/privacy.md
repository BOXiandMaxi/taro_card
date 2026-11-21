# Tarot Reading privacy notice draft

When you register, Tarot Reading stores your normalized email address and an
Argon2 password hash. We use a browser session cookie to keep you signed in.
The database stores a hash of the session token. The session expires after
seven days by default, and signing out revokes it. A separate browser cookie
helps protect sign-in and registration requests from forgery.

We store the selected category and spread, your question, the cards you draw
and any saved interpretation. Your account history contains readings created
while signed in and guest readings you claim by requesting an interpretation
after signing in. A guest reading is accessible from the browser that holds its
private reading cookie. Claiming a reading removes this guest access.
Guest access expires 30 days after creation
by default, and a scheduled cleanup can then remove the reading from the
database. You can delete individual readings you can access. Member readings
remain until deleted.

When external AI processing is enabled and your request uses it, Tarot Reading sends
your question text, reading ID, category and spread, and revealed card details
and meanings to the selected provider (OpenAI or Google Gemini) to generate an interpretation. The request does not
include your email, password, session cookie or guest capability. Avoid adding
personal or sensitive information to custom questions. OpenAI requests set
`store: false`. Google's free Gemini tier may use content to improve its products;
review the provider's current terms before enabling it. Deleting a reading from
Tarot Reading does not send a deletion request to the external provider.

We use pseudonymous client address buckets to limit authentication attempts and
account IDs to limit AI attempts. When a reading is
deleted, its question, cards and cached result are removed from the
application database. Usage records keep the quota scope, model, timestamp,
outcome and reported usage for accounting without a link to the reading.
A creation retry hash may remain to prevent a delayed retry from restoring
the reading.

Before publication, add the operator's privacy contact, account deletion
process, applicable provider terms, and verified retention periods for backups,
session records, rate-limit records, retry hashes and AI usage records.
