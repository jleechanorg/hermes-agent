#!/bin/bash
# Inventory installed WorldAI sim apps: Release bundle?, native modules the current JS needs,
# and whether the app's AsyncStorage has an auth-token KEY (key-name presence only — values are
# never read or printed).
#
# usage: scan-sim-apps.sh
set -u
DEVICES="$HOME/Library/Developer/CoreSimulator/Devices"

for d in "$DEVICES"/*/; do
  ud=$(basename "$d")
  app=$(ls -d "$d"data/Containers/Bundle/Application/*/*.app 2>/dev/null | head -1)
  [ -n "$app" ] || continue
  ident=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$app/Info.plist" 2>/dev/null)
  [ "$ident" = "ai.worldarchitect.app" ] || continue

  exe=$(ls "$app"/WorldAIClaw "$app"/WorldAI "$app"/seedhead 2>/dev/null | head -1)
  push_mod=0; secure_mod=0
  if [ -n "$exe" ]; then
    push_mod=$(strings -a "$exe" 2>/dev/null | grep -c "ExpoPushTokenManager")
    secure_mod=$(strings -a "$exe" 2>/dev/null | grep -c "ExpoSecureStore")
  fi

  has_bundle=no; [ -f "$app/main.jsbundle" ] && has_bundle=yes

  signed_in=unknown
  for cont in "$d"data/Containers/Data/Application/*/; do
    meta="$cont.com.apple.mobile_container_manager.metadata.plist"
    [ -f "$meta" ] || continue
    [ "$(/usr/libexec/PlistBuddy -c "Print :MCMMetadataIdentifier" "$meta" 2>/dev/null)" = "ai.worldarchitect.app" ] || continue
    manifest="$cont/Library/Application Support/ai.worldarchitect.app/RCTAsyncLocalStorage_V1/manifest.json"
    if [ -f "$manifest" ]; then
      signed_in=$(python3 - "$manifest" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    print("unknown"); raise SystemExit
# key-name presence only; values are never loaded into output
print("yes" if "@worldclaw/auth-token" in data else "no")
PY
)
    else
      signed_in=no
    fi
  done

  echo "$ud release_bundle=$has_bundle push_mod=$push_mod secure_mod=$secure_mod auth_key=$signed_in app=$(basename "$app")"
done
