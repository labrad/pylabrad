package org.labrad.client;

import java.util.ArrayList;
import java.util.List;

import com.google.gwt.core.client.JavaScriptObject;

public class JsArray<T> extends JavaScriptObject {
    public static native <T> JsArray<T> create() /*-{
        return [];
    }-*/;

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

	public static <T> List<T> toList(JsArray<T> arr) {
		List<T> list = new ArrayList<T>();
		for (int i = 0; i < arr.size(); i++) {
			list.add(arr.get(i));
		}
		return list;
	}
}