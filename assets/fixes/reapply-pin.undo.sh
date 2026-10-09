#!/bin/sh
# The undo of reapply-pin: the drone puts the set-aside record back (`drone pin restore`), or,
# when it has written its own record since, keeps the set-aside one beside it, renamed.
D="${HIVE_DRONE:-${HIVE_HOME:-$HOME/.hive}/bin/drone}"
exec "$D" pin restore
