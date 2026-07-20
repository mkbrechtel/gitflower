#!/bin/sh
# Install smoke test for the gitflower .deb — runs inside the test stage of
# the Containerfile (no systemd in a build container, so the web service is
# exercised directly as the gitflower user the package created).
set -eu

echo "== package sanity"
gitflower --version
ls /usr/share/man/man1/gitflower.1* >/dev/null
id gitflower
test -f /etc/gitflower/config.yaml
test -f /usr/lib/systemd/system/gitflower.service

echo "== state directory (systemd creates it on the host; do it here)"
install -d -o gitflower -g gitflower /var/lib/gitflower /var/lib/gitflower/repos

echo "== create a repo as the service user, seed it"
runuser -u gitflower -- gitflower --config /etc/gitflower/config.yaml create demo.git
# seed as the same user — git's ownership check applies to root too
runuser -u gitflower -- sh -c 'git clone -q /var/lib/gitflower/repos/demo.git /tmp/work \
    && cd /tmp/work \
    && git checkout -q -b main \
    && echo "# demo" > README.md \
    && git add . \
    && git -c user.name=smoke -c user.email=smoke@test.invalid commit -qm initial \
    && git push -q origin main'

echo "== hook engine end to end"
# The hooks belong to the repository being pushed to: enforcement is
# server-side, so `init` and `install` run in the bare repo and a client
# cannot opt out of them.
runuser -u gitflower -- sh -c 'cd /var/lib/gitflower \
    && git init -q --bare hooked-remote.git \
    && cd hooked-remote.git && gitflower init >/dev/null && gitflower install >/dev/null \
    && test -x hooks/pre-receive && test -x hooks/post-receive'
runuser -u gitflower -- sh -c 'cd /var/lib/gitflower && git init -q hooked && cd hooked \
    && git checkout -q -b main \
    && echo hi > f.txt && git add . \
    && git -c user.name=s -c user.email=s@t.invalid commit -qm c1 \
    && git remote add origin ../hooked-remote.git \
    && { git push origin main 2>&1 | grep -q "Direct push to protected branch" \
         || { echo "protected push was not rejected"; exit 1; }; } \
    && { git push --no-verify origin main 2>&1 | grep -q "Direct push to protected branch" \
         || { echo "--no-verify bypassed a server-side hook"; exit 1; }; } \
    && git checkout -q -b issues/1 \
    && git push -q origin issues/1'
echo "hook engine OK"

echo "== a merge request, recorded by the push that carried it"
runuser -u gitflower -- sh -c 'cd /var/lib/gitflower/hooked \
    && git -c user.name=s -c user.email=s@t.invalid commit -q --allow-empty \
         -m "MR: the smoke test asks to merge" \
    && git push -q origin issues/1'
# read it back where the record lives: the bare repository the hook wrote it
# into, whose HEAD names the mainline
runuser -u gitflower -- sh -c 'cd /var/lib/gitflower/hooked-remote.git \
    && git for-each-ref --format="%(refname)" refs/mrs/ | grep -q "/request$" \
       || { echo "the push did not record a merge request"; exit 1; }'
runuser -u gitflower -- sh -c 'cd /var/lib/gitflower/hooked-remote.git \
    && gitflower mr list | grep -q "the smoke test asks to merge" \
       || { echo "mr list did not show the request"; exit 1; }'
echo "merge requests OK"

echo "== web service (run directly; systemd owns it on a real host)"
# a dedicated port: rootless `podman build` RUN steps can share the host
# network, where 8747 may be a deployed gitflower answering for this one
PORT=18747
runuser -u gitflower -- gitflower --config /etc/gitflower/config.yaml web --addr "127.0.0.1:$PORT" >/tmp/server.log 2>&1 &
SERVER=$!
cleanup() {
    status=$?
    kill $SERVER 2>/dev/null || true
    if [ $status -ne 0 ]; then
        echo "== SMOKE FAILED (exit $status) — server log:"
        cat /tmp/server.log
    fi
}
trap cleanup EXIT
i=0
until curl -fsS -o /dev/null http://127.0.0.1:$PORT/ 2>/dev/null; do
    i=$((i + 1)); [ $i -lt 100 ] || { echo "server never came up"; cat /tmp/server.log; exit 1; }
    sleep 0.2
done

echo "== three representations from one URL"
curl -fsS http://127.0.0.1:$PORT/repos/demo.git | grep -q '<nav class="gf-nav">'
curl -fsS -H 'GF-Fragment: 1' http://127.0.0.1:$PORT/repos/demo.git | grep -qv '<nav'
curl -fsS -H 'Accept: application/json' http://127.0.0.1:$PORT/repos/demo.git \
    | python3 -c 'import json,sys; d = json.load(sys.stdin); assert [b["name"] for b in d["branches"]] == ["main"], d; assert d["graph"]["rows"]'
curl -fsS "http://127.0.0.1:$PORT/repos/demo.git/tree/main/README.md?format=raw" | grep -qx '# demo'

echo "== read-only smart-HTTP clone"
git clone -q http://127.0.0.1:$PORT/repos/demo.git /tmp/cloned
grep -qx '# demo' /tmp/cloned/README.md
cd /tmp/cloned
if git push -q origin main 2>/dev/null; then
    echo "push over HTTP unexpectedly succeeded"; exit 1
fi
cd /

echo "== smoke test PASSED"
