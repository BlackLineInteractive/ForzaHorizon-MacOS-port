# Sourced by the run scripts: honour a shared benchmark lock.
#
# Several people/jobs share the test machine; one can take a clean window for measurements by
# creating BENCH_LOCK (content: "owner expiry-epoch purpose"). While someone else holds an
# unexpired lock, starting the game would spoil their numbers: refuse (status 3).
# BENCH_LOCK overrides the lock path; BENCH_OWNER names us (default forza);
# FORZA_IGNORE_LOCK=1 skips the check.
bench_lock_check() {
    local lock="${BENCH_LOCK:-${TMPDIR:-/tmp}/BENCH_LOCK}"
    [ "${FORZA_IGNORE_LOCK:-0}" = 1 ] && return 0
    [ -f "$lock" ] || return 0
    local owner expiry purpose
    read -r owner expiry purpose < "$lock" || true
    [ "$owner" = "${BENCH_OWNER:-forza}" ] && return 0
    if [ -n "$expiry" ] && [ "$expiry" -gt "$(date +%s)" ] 2>/dev/null; then
        echo "benchmark lock held by $owner until $(date -d @"$expiry" +%T) ($purpose); not starting" >&2
        return 3
    fi
    return 0
}
