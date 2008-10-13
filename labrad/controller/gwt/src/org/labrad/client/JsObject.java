package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;

public class JsObject extends JavaScriptObject {
	protected JsObject() {}
	
	public final native String getString(String key) /*-{ return this[key]; }-*/;
	public final native JavaScriptObject get(String key) /*-{ return this[key]; }-*/;
	
	public final native JsArray<String> keys() /*-{
	    var keys = [];
	    for (key in this) {
	    	keys.push(key);
	    }
	    return keys;
	}-*/;
}
