package org.labrad.client;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.google.gwt.core.client.JavaScriptObject;

public class JsMap<K, V> extends JavaScriptObject {
    public static native <K, V> JsMap<K, V> create() /*-{
        return {};
    }-*/;

    protected JsMap() {
    }

    public final native V get(K key) /*-{
        return this[key];
    }-*/;

    public final native void put(K key, V value) /*-{
        this[key] = value;
    }-*/;

    public final native JsArray<K> keys() /*-{
        var keys = [];
        for (key in this) {
        	keys.push(key);
        }
        return keys;
    }-*/;
    
    public final native JsArray<V> values() /*-{
	    var values = [];
	    for (key in this) {
	    	values.push(this[key]);
	    }
	    return values;
	}-*/;
    
    public static <K, V> List<K> keyList(JsMap<K, V> jsmap) {
    	return JsArray.toList(jsmap.keys());
    }

    public static <K, V> List<V> valueList(JsMap<K, V> jsmap) {
    	return JsArray.toList(jsmap.values());
    }
    
	public static <K, V> Map<K, V> toMap(JsMap<K, V> jsmap) {
		Map<K, V> map = new HashMap<K, V>();
		for (K k : keyList(jsmap)) {
			map.put(k, jsmap.get(k));
		}
		return map;
	}
}
