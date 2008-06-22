package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;

public class JsString extends JavaScriptObject {
    protected JsString() {
    }
    
    public final native String stringValue() /*-{
        return this;
    }-*/;
}
