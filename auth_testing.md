[Saved playbook — see integration_playbook_expert_v2 output Phase 13.]

# Auth-Gated App Testing Playbook

Step 1: Create Test User & Session

mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"

Step 2: Backend
curl -X GET "{API}/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"

Step 3: Browser
Set cookie session_token, navigate, verify dashboard renders.

Notes for NXT1:
- Admin gate at /access (password 555) issues a different JWT (`role=admin`) that
  also passes verify_token. Google sessions are stored in user_sessions and
  honoured by the same verify_token via cookie/Bearer fallback.
- Test users live in `users` collection; sessions in `user_sessions`.
