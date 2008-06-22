package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.json.client.JSONValue;
import com.google.gwt.user.client.ui.ClickListener;
import com.google.gwt.user.client.ui.HorizontalPanel;
import com.google.gwt.user.client.ui.Image;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.PushButton;
import com.google.gwt.user.client.ui.Widget;

public class IPEntry extends HorizontalPanel {
	private final IPLists parent;
	private final String address, method;
	
	private final Image ALLOWED_IMG = new Image("tick.gif");
	private final Image BLOCKED_IMG = new Image("cross.gif");
	
	private JSONTransport transport;
	
	public IPEntry(IPLists parent, JSONTransport transport, String address, boolean state) {
		this.address = address;
		this.method = state ? "blacklist" : "whitelist";
		this.parent = parent;
		this.transport = transport;
		
		PushButton button = new PushButton(state ? ALLOWED_IMG : BLOCKED_IMG);
		button.addClickListener(new ClickListener() {
			public void onClick(Widget sender) {
				switchEntry();
			}
		});
		add(button);
		Label lbl = new Label(address);
		lbl.addStyleDependentName("padded");
		add(lbl);
	}
	
	public void switchEntry() {
        JSONArray args = new JSONArray();
        args.set(0, new JSONString(address));
        transport.invokeMethod(method, args, new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable error) {
                // nothing yet
            }
            
            public void onResponseReceived(JavaScriptObject response) {
                parent.fetchTable();
            }
        });
    }
}
