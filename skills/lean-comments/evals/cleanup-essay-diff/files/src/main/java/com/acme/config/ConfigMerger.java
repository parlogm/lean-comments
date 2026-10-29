package com.acme.config;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Merges nested configuration maps.
 *
 * <p>There are two public operations because the special {@code "override"} key behaves differently
 * when saving a config versus when computing the effective config a workspace sees, and we found it
 * clearer to give each its own method than to thread a mode parameter through every call site.
 *
 * <p>Neither method modifies its arguments. Each returns a new map, which matters because the parent
 * configs passed in usually come straight from the cache and are shared between requests.
 */
public final class ConfigMerger {

    private ConfigMerger() {}

    // ---- writing ----------------------------------------------------------------------------

    /**
     * Merges an incoming change into a stored config. In this mode {@code "override"} has no special
     * meaning and is merged like any other key. Both operations used to live in one method, until
     * ABC-812 split them when the meaning of override changed again in ABC-831.
     *
     * @param base the stored config
     * @param patch the incoming change
     * @return a new merged map
     */
    public static Map<String, Object> deepMerge(Map<String, Object> base, Map<String, Object> patch) {
        Map<String, Object> out = new LinkedHashMap<>(base);
        patch.forEach((k, v) -> out.merge(k, v, ConfigMerger::mergeValues));
        return out;
    }

    // ---- resolving --------------------------------------------------------------------------

    // Tenant configs written before 2025 may still carry "override"; it is ignored on read.
    public static Map<String, Object> inheritMerge(Map<String, Object> parent, Map<String, Object> child) {
        // Since ABC-831 the override flag is now only set on workspaces; tenant-level sections no longer
        // carry an override key, so for them we always take the merge path at the bottom. A workspace
        // with override=true takes its own section and replaces the parent's wholesale rather than
        // merging key by key, which is how the admin UI implements "stop inheriting from the tenant".
        if (Boolean.TRUE.equals(child.get("override"))) {
            return new LinkedHashMap<>(child);
        }
        return deepMerge(parent, child);
    }

    @SuppressWarnings("unchecked")
    private static Object mergeValues(Object a, Object b) {
        // Nested maps are merged recursively; for anything else the incoming value simply wins. We
        // considered merging lists item by item as well, but the admin UI always submits complete
        // lists, so an item-level merge would bring back entries the admin had just deleted.
        if (a instanceof Map && b instanceof Map) {
            return deepMerge((Map<String, Object>) a, (Map<String, Object>) b);
        }
        return b;
    }
}
