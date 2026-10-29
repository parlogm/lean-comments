package com.example.catalog.pricing;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

public class PriceListCache {

    private final Map<String, List<String>> entries = new ConcurrentHashMap<>();
    private final Function<String, List<String>> loader;

    public PriceListCache(Function<String, List<String>> loader) {
        this.loader = loader;
    }

    public List<String> find(String storeId) {
        return entries.computeIfAbsent(key(storeId), k -> loader.apply(storeId));
    }

    public void evict(String storeId) {
        entries.remove(key(storeId));
    }

    private static String key(String storeId) {
        return "price-lists:" + storeId;
    }
}
