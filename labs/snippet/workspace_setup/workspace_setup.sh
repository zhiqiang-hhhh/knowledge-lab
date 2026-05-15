#!/bin/bash
set -e

# ========== 配置 ==========
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_ROOT="$HOME/workspace/doris"
CODE_ROOT="$HOME/code"   # 假设 code/doris 在这里
DEFAULT_CODE="doris"                 # 默认二进制目录名

# ========== 函数 ==========

create_version() {
    local version="$1"
    local vdir="$WORKSPACE_ROOT/$version"

    echo "[INFO] Creating Doris workspace for version: $version"
    mkdir -p "$vdir"

    # ---------- FE ----------
    local fe="$vdir/fe1"
    mkdir -p "$fe/doris-meta" "$fe/log" "$fe/plugins" "$fe/temp_dir"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/fe/bin"         "$fe/bin"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/fe/custom_lib"  "$fe/custom_lib"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/fe/lib"         "$fe/lib"
    cp -r "$SCRIPT_DIR/base_fe_conf" "$fe/conf"

    # ---------- ASAN BE ----------
    local asan="$vdir/ASAN/be1"
    mkdir -p "$asan/lib" "$asan/log" "$asan/storage" "$asan/connectors" "$asan/custom_lib" "$asan/dict"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/be/build_ASAN/src/service/doris_be" "$asan/lib/doris_be"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/be/bin"         "$asan/bin"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/be/connectors"  "$asan/connectors"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/be/custom_lib"  "$asan/custom_lib"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/be/dict"        "$asan/dict"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/be/lib/java_extensions"    "$asan/lib/java_extensions"
    cp -r "$SCRIPT_DIR/base_be_conf" "$asan/conf"

    # ---------- RELEASE BE ----------
    local rel="$vdir/RELEASE/be1"
    mkdir -p "$rel/lib"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/be/build_Release/src/service/doris_be" "$rel/lib/doris_be"
    ln -snf "$CODE_ROOT/$DEFAULT_CODE/output/be/lib/java_extensions"         "$rel/lib/java_extensions"
    for item in bin conf connectors custom_lib dict log storage; do
        ln -snf "../../ASAN/be1/$item" "$rel/$item"
    done

    echo "[OK] Workspace for $version created."
}

switch_bin() {
    local target="$1"
    echo "[INFO] Switching binaries to: $target"

    find "$WORKSPACE_ROOT" -type l | while read -r link; do
        if [[ "$link" =~ /lib/doris_be$ ]]; then
            if [[ "$link" =~ /ASAN/ ]]; then
                ln -snf "$CODE_ROOT/$target/be/build_ASAN/src/service/doris_be" "$link"
            else
                ln -snf "$CODE_ROOT/$target/be/build_Release/src/service/doris_be" "$link"
            fi
        elif [[ "$link" =~ /bin$ ]]; then
            if [[ "$link" =~ /fe1/bin$ ]]; then
                ln -snf "$CODE_ROOT/$target/output/fe/bin" "$link"
            else
                ln -snf "$CODE_ROOT/$target/output/be/bin" "$link"
            fi
        elif [[ "$link" =~ /custom_lib$ && "$link" =~ /fe1/ ]]; then
            ln -snf "$CODE_ROOT/$target/output/fe/custom_lib" "$link"
        elif [[ "$link" =~ /custom_lib$ ]]; then
            ln -snf "$CODE_ROOT/$target/output/be/custom_lib" "$link"
        elif [[ "$link" =~ /connectors$ ]]; then
            ln -snf "$CODE_ROOT/$target/output/be/connectors" "$link"
        elif [[ "$link" =~ /dict$ ]]; then
            ln -snf "$CODE_ROOT/$target/output/be/dict" "$link"
        elif [[ "$link" =~ /fe1/lib$ ]]; then
            ln -snf "$CODE_ROOT/$target/output/fe/lib" "$link"
        fi
    done
    echo "[OK] Binaries switched to: $target"
}

# ========== 主入口 ==========
case "$1" in
    create)
        if [ -z "$2" ]; then
            echo "Usage: $0 create <version>"
            exit 1
        fi
        create_version "$2"
        ;;
    switch)
        if [ -z "$2" ]; then
            echo "Usage: $0 switch <code_dir_name>"
            exit 1
        fi
        switch_bin "$2"
        ;;
    *)
        echo "Usage: $0 {create <version>|switch <code_dir_name>}"
        exit 1
        ;;
esac
