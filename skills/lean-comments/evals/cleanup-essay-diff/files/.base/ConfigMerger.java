package com.acme.config;

import java.util.LinkedHashMap;
import java.util.Map;

public final class ConfigMerger {

    private ConfigMerger() {}

    public static Map<String, Object> deepMerge(Map<String, Object> base, Map<String, Object> patch) {
        Map<String, Object> out = new LinkedHashMap<>(base);
        patch.forEach((k, v) -> out.merge(k, v, ConfigMerger::mergeValues));
        return out;
    }

    // Tenant configs written before 2025 may still carry "override"; it is ignored on read.
    public static Map<String, Object> inheritMerge(Map<String, Object> parent, Map<String, Object> child) {
        return deepMerge(parent, child);
    }

    @SuppressWarnings("unchecked")
    private static Object mergeValues(Object a, Object b) {
        if (a instanceof Map && b instanceof Map) {
            return deepMerge((Map<String, Object>) a, (Map<String, Object>) b);
        }
        return b;
    }
}
