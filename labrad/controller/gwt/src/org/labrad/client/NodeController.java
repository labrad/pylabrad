package org.labrad.client;

import com.google.gwt.core.client.EntryPoint;
import com.google.gwt.http.client.Request;
import com.google.gwt.http.client.RequestBuilder;
import com.google.gwt.http.client.RequestCallback;
import com.google.gwt.http.client.Response;
import com.google.gwt.json.client.JSONNumber;
import com.google.gwt.json.client.JSONObject;
import com.google.gwt.json.client.JSONParser;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.user.client.ui.RootPanel;
import com.google.gwt.user.client.ui.TabPanel;
import com.google.gwt.user.client.ui.VerticalPanel;

/**
 * Entry point classes define <code>onModuleLoad()</code>.
 */
public class NodeController implements EntryPoint, RequestCallback {
	public void onModuleLoad() {
	    RequestBuilder request = new RequestBuilder(RequestBuilder.GET, "/api/get_transport_ID");
	    try {
	        JSONObject jo = new JSONObject();
	        jo.put("id", new JSONNumber(0));
	        request.sendRequest(null, this);
	    } catch (Exception e) {
	        // do nothing
	    }
	}
	
	public void onError(Request request, Throwable exception) {
	}
	    
	public void onResponseReceived(Request request, Response response) {
	    String ID = ((JSONString)((JSONObject)JSONParser.parse(response.getText())).get("result")).stringValue();
	    
        JSONTransport transport = new JSONTransport("/api/transport", ID);
        
        TabPanel tabs = new TabPanel();
        tabs.add(new ControlPanel(transport), "Nodes");
        tabs.add(new IPLists(transport), "Security");
        
        VerticalPanel logger = new VerticalPanel();
        transport.setLogger(logger);
        tabs.add(logger, "Log");

        tabs.selectTab(0);
        tabs.setWidth("100%");
        RootPanel.get("main").add(tabs);
    }
}
