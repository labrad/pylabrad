package org.labrad.client;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.http.client.Request;
import com.google.gwt.http.client.RequestBuilder;
import com.google.gwt.http.client.RequestCallback;
import com.google.gwt.http.client.RequestException;
import com.google.gwt.http.client.Response;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONObject;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.user.client.Command;
import com.google.gwt.user.client.DeferredCommand;

public class JSONTransport {
	private final String baseurl;
	private LogWindow logger;
	private Command pull;
	private int nextId;
    private Map<String, JSONRequestCallback> requestHandlers;
    private Map<String, List<JSONMessageListener>> messageListeners;
    private RequestBuilder pullRequester, pushRequester;
	
    private int LOG_LENGTH = 10;
    
	public JSONTransport(String url, String ID) {
		baseurl = url;
		nextId = 1;
        requestHandlers = new HashMap<String, JSONRequestCallback>();
        messageListeners = new HashMap<String, List<JSONMessageListener>>();
        
        pullRequester = new RequestBuilder(RequestBuilder.POST, baseurl + "/pull?ID=" + ID);
        pushRequester = new RequestBuilder(RequestBuilder.POST, baseurl + "/push?ID=" + ID);
        
        // start pulling down responses
		pull = new Command() {
			public void execute() {
				pullResponses();
			}
		};
		pull.execute();
	}
	
	public void setLogger(LogWindow logger) {
		this.logger = logger;
	}
	
    private void log(String message) {
    	logger.log(message);
    }
    
	private void pullResponses() {
		try {
            pullRequester.sendRequest(null, new RequestCallback() {
                public void onError(Request request, Throwable exception) {
                    //
                }
    
                public void onResponseReceived(Request request, Response response) {
                    JsArray<JsResponse> responses = JsEvaluator.eval(response.getText()).cast();
                    for (int i = 0; i < responses.size(); i++) {
                    	handleResponse(responses.get(i));
                    }
                    DeferredCommand.addCommand(pull);
                }
            });
        } catch (RequestException e) {
            //
        }
	}
	
	public void addMessageListener(String message, JSONMessageListener listener) {
	    if (!messageListeners.containsKey(message)) {
	        messageListeners.put(message, new ArrayList<JSONMessageListener>());
	    }
	    messageListeners.get(message).add(listener);
	}
	
	public void removeMessageListener(String message, JSONMessageListener listener) {
	    if (messageListeners.containsKey(message)) {
	        messageListeners.get(message).remove(listener);
	    }
	}
	
	private void handleResponse(JsResponse response) {
		if (response.isMessage()) {
			String message = response.getString("message");
			JsArray<JavaScriptObject> args = response.get("args").cast();
			JavaScriptObject kw = response.get("kw");
			handleMessage(message, args, kw);
			
		} else if (response.isResult()) {
			String id = response.getString("id");
			JavaScriptObject result = response.get("result");
			handleResult(id, result);
		
		} else if (response.isError()) {
			String id = response.getString("id");
			String error = response.getString("error");
			handleError(id, error);
		}
	}

	private void handleMessage(String message, JsArray<JavaScriptObject> args, JavaScriptObject kw) {
		log("Message: " + message +
		    ".  args: " + args.toString() +
		    ".  kw: " + kw.toString());
		//JavaScriptObject[] argsArray = JsArray.toArray(args);
		JsObject kwObject = (JsObject) kw;
		JsArray<String> keys = kwObject.getKeys();
		Map<String, String> kwMap = new HashMap<String, String>();
		for (int i = 0; i < keys.size(); i++) {
		    kwMap.put(keys.get(i), kwObject.get(keys.get(i)));
		}
		if (messageListeners.containsKey(message)) {
		    for (JSONMessageListener listener : messageListeners.get(message)) {
		        listener.onMessage(args, kwMap);
		    }
		}
	}
	
	private void handleResult(String id, JavaScriptObject result) {
        //log("Result (" + id + "): " + result.toString());
        JSONRequestCallback callback = requestHandlers.get(id);
        requestHandlers.remove(id);
        if (callback != null) callback.onResponseReceived(result);
	}
	
	private void handleError(String id, String error) {
		log("Error (" + id + "): " + error);
        JSONRequestCallback callback = requestHandlers.get(id);
        requestHandlers.remove(id);
        if (callback != null) callback.onError(new Exception(error));
	}
	
    public void invokeMethod(String method) {
        invokeMethod(method, null);
    }
    
    public void invokeMethod(String method, JSONRequestCallback callback) {
        JSONArray args = new JSONArray();
        invokeMethod(method, args, callback);
    }
    
    public void invokeMethod(String method, JSONArray args, JSONRequestCallback callback) {
        JSONObject kw = new JSONObject();
        invokeMethod(method, args, kw, callback);
    }
    
	public void invokeMethod(String method, JSONArray args, JSONObject kw, JSONRequestCallback callback) {
        final String id = Integer.toString(nextId);
        nextId += 1;
        if (callback != null) {
        	requestHandlers.put(id, callback);
        }
        
        JSONObject data = new JSONObject();
        data.put("id", new JSONString(id));
        data.put("method", new JSONString(method));
        data.put("args", args);
        data.put("kw", kw);

        try {
            pushRequester.sendRequest(data.toString(), new RequestCallback() {
                public void onError(Request request, Throwable exception) {
                    if (requestHandlers.containsKey(id)) {
                        requestHandlers.remove(id);
                    }
                }
    
                public void onResponseReceived(Request request, Response response) {
                    // nothing for now
                }
            });
        } catch (RequestException e) {
            if (requestHandlers.containsKey(id)) {
                requestHandlers.remove(id);
            }
        }
	}
    
	private static class JsResponse extends JavaScriptObject {
    	protected JsResponse() {}
        
    	public final native boolean isMessage() /*-{ return "message" in this; }-*/;
    	public final native boolean isResult() /*-{ return "result" in this; }-*/;
        public final native boolean isError() /*-{ return "error" in this; }-*/;
        public final native JavaScriptObject get(String key) /*-{ return this[key]; }-*/;
        public final native String getString(String key) /*-{ return this[key]; }-*/;
        public final native <T> T get(String key, Class<T> cls) /*-{ return this[key]; }-*/;
	}
	
	private static class JsObject extends JavaScriptObject {
	    protected JsObject() {}
        
        public final native JsArray<String> getKeys() /*-{
            var keys = [];
            for (var key in this) {
                keys.push(key);
            }
            return keys;
        }-*/;
        
        public final native String get(String key) /*-{ return this[key]; }-*/;
	}
	
    public interface JSONRequestCallback {
        public void onError(Throwable error);
        public void onResponseReceived(JavaScriptObject response);
    }
    
    public interface JSONMessageListener {
        public void onMessage(JsArray<JavaScriptObject> args, Map<String, String> kw);
    }
}
