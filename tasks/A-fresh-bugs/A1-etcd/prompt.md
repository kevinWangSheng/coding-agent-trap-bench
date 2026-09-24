Bug report for the etcd repository in ./repo.

We run etcd with a backend quota (`--quota-backend-bytes`). Plain `Put` requests and plain transactions correctly get rejected with "etcdserver: mvcc: database space exceeded" once the quota would be exceeded. However, a client can get around the quota: if the `Put` operations are wrapped inside a *nested* transaction (a `Txn` whose `success` or `failure` branch contains another `Txn` that performs the `Put`s), the request is accepted and the database keeps growing past the quota.

Nested transactions must be accounted for the same way as their flat equivalents, in both branches.

Please fix this in the server code and add or update unit tests that cover it. Run the relevant tests before you finish.
