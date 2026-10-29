# Project material access

Research groups organize people, research directions, and governance ownership.
A project's group affiliation does not automatically share its material with
everyone in the group. The project settings panel and material details display
this affiliation separately from the access scope.

For project material, source-project membership grants baseline access to
public and internal content. Confidential, restricted, and top-secret content
continues to require the applicable explicit grants. Owners retain their
revision-pinned policies; administrators can inspect project metadata, but
administrative privileges alone do not grant content access.

Linking material to another project does not itself grant that project's members
access. Cross-project use requires an explicit content policy, such as an
approved access request. A project-scoped group policy must name its required
project. Unscoped group policies do not grant access to project material.

New project and project-session uploads no longer create automatic group-wide
content policies. Existing unscoped group policies are ignored for project
material by the authorization evaluator. Existing group records, policies, and
project links are retained, so deployment needs no database cleanup or migration.
For legacy material without a source project, linked-project membership remains
the baseline until its source project can be identified.

Material access requests distinguish personal reading from project-specific
requests. A previous approval that no longer grants reading does not block a
new request; a pending request blocks duplicates. Deleting a managed file or
granting its use in AI training requires both management and reading permission.

When a duplicate upload has no visible locations, the upload dialog offers a
personal reading request using the source ID and matching content hash. The
request response contains only a request ID and status. Hidden material titles
remain redacted in the requester's request list until metadata access is granted;
the source ID identifies the uploaded file in the meantime. Approved material
has a detail link in the library's request list and can be reused by uploading
the same file again.

Requests can be reviewed by the material owner or manager, the source project's
owner, or an administrator. A PI role or group membership alone does not grant
review authority over another project's material. The pending queue is filtered
by that authority, and both approval and rejection enforce it on the server.

## Access request notifications

The global header provides a persistent notification inbox and unread badge.
New requests notify active material owners, managers, source-project owners, and
administrators who can review them. Approval and rejection notify the requester.
Deciding or canceling a request marks its pending review notifications as read.
Notification writes share the request transaction, so failed submissions and
repeated decisions do not create messages.

Notifications use generic localized descriptions without hidden material names.
Opening one marks it as read and opens the relevant library tab with the request
highlighted. Only the recipient can list or mark their notifications as read.
The inbox refreshes every 30 seconds while the page is active, on window focus,
and when opened. Notifications persist across sign-ins; no email or external
push delivery is involved.

Deployments must run `alembic upgrade head` from `backend/` before serving the
notification feature. Revision `t4u5v6w7x8y9` creates the notification table and
backfills active baseline reviewers for existing pending requests.
