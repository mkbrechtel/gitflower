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
runuser -u gitflower -- sh -c 'cd /var/lib/gitflower && git init -q hooked && cd hooked \
    && git checkout -q -b main \
    && echo hi > f.txt && git add . \
    && git -c user.name=s -c user.email=s@t.invalid commit -qm c1 \
    && gitflower init >/dev/null && gitflower install >/dev/null \
    && git init -q --bare ../hooked-remote.git \
    && git remote add origin ../hooked-remote.git \
    && { git push origin main 2>&1 | grep -q "Direct push to protected branch" \
         || { echo "protected push was not rejected"; exit 1; }; } \
    && git checkout -q -b issues/1 \
    && git push -q origin issues/1'
echo "hook engine OK"

echo "== web service (run directly; systemd owns it on a real host)"
runuser -u gitflower -- gitflower --config /etc/gitflower/config.yaml web &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
i=0
until curl -fsS -o /dev/null http://127.0.0.1:8747/; do
    i=$((i + 1)); [ $i -lt 50 ] || { echo "server never came up"; exit 1; }
    sleep 0.2
done

echo "== three representations from one URL"
curl -fsS http://127.0.0.1:8747/repos/demo.git | grep -q '<nav class="gf-nav">'
curl -fsS -H 'GF-Fragment: 1' http://127.0.0.1:8747/repos/demo.git | grep -qv '<nav'
curl -fsS -H 'Accept: application/json' http://127.0.0.1:8747/repos/demo.git \
    | python3 -c 'import json,sys; d = json.load(sys.stdin); assert [b["name"] for b in d["branches"]] == ["main"], d; assert d["graph"]["rows"]'
curl -fsS 'http://127.0.0.1:8747/repos/demo.git/tree/main/README.md?format=raw' | grep -qx '# demo'

echo "== read-only smart-HTTP clone"
git clone -q http://127.0.0.1:8747/repos/demo.git /tmp/cloned
grep -qx '# demo' /tmp/cloned/README.md
cd /tmp/cloned
if git push -q origin main 2>/dev/null; then
    echo "push over HTTP unexpectedly succeeded"; exit 1
fi
cd /

echo "== smoke test PASSED"
