package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;

public class JsArray<T> extends JavaScriptObject {
    public static native <T> JsArray<T> create() /*-{
        return [];
    }-*/;
    
    @SuppressWarnings("unchecked")
    public static <T> T[] toArray(JsArray<T> orig) {
        T[] array = (T[]) new Object[orig.size()];
        for (int i = 0; i < orig.size(); i++) {
            array[i] = orig.get(i);
        }
        return array;
    }

    protected JsArray() {
    }

    public final native T get(int index) /*-{
        return this[index];
    }-*/;

    public final native int size() /*-{
        return this.length;
    }-*/;

    public final native void put(int index, T value) /*-{
        this[index] = value;
    }-*/;
}