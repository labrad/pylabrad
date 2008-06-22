package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;

public class JsEvaluator {
    public static native JavaScriptObject eval(String s) /*-{
        return eval(s);
    }-*/;
}
