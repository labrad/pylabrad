package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.user.client.ui.Button;
import com.google.gwt.user.client.ui.ClickListener;
import com.google.gwt.user.client.ui.Grid;
import com.google.gwt.user.client.ui.HorizontalPanel;
import com.google.gwt.user.client.ui.KeyboardListenerAdapter;
import com.google.gwt.user.client.ui.TextBox;
import com.google.gwt.user.client.ui.VerticalPanel;
import com.google.gwt.user.client.ui.Widget;

public class IPLists extends VerticalPanel {
    TextBox address;
	Grid ipTable;
	JSONTransport transport;
	
	private static class IpEntry extends JavaScriptObject {
	    protected IpEntry() {
	    }
	    
	    public final native String getAddress() /*-{
	        return this[0];
	    }-*/;
	    
	    public final native boolean isAllowed() /*-{
	        return this[1];
	    }-*/;
	}
	
	public void fetchTable() {
	    transport.invokeMethod("iplist", new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable exception) {
                //resp.setText("Request failed with an error: " + exception.toString());
            }

            @SuppressWarnings("unchecked")
            public void onResponseReceived(JavaScriptObject response) {
                makeTable((JsArray<IpEntry>) response);
            }
        });
    }
    
    public void makeTable(JsArray<IpEntry> iplist) {
    	if (ipTable != null) remove(ipTable);
        ipTable = new Grid(iplist.size(), 1);
        for (int i = 0; i < iplist.size(); i++) {
            IpEntry ip = iplist.get(i);
        	ipTable.setWidget(i, 0, new IPEntry(this, this.transport, ip.getAddress(), ip.isAllowed()));
        }
        add(ipTable);
    }
    
    public void addAddress() {
        if (address.getText().length() == 0) {
            return;
        }
        JSONArray args = new JSONArray();
        args.set(0, new JSONString(address.getText()));
        address.setText("");
        transport.invokeMethod("whitelist", args, new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable error) {
                // nothing yet
            }
            
            public void onResponseReceived(JavaScriptObject response) {
                fetchTable();
            }
        });
    }
    
	public IPLists(JSONTransport transport) {
		ipTable = null;
		this.transport = transport;
		address = new TextBox();
		address.addKeyboardListener(new KeyboardListenerAdapter() {
            public void onKeyPress(Widget sender, char keyCode, int modifiers) {
                if (keyCode == (char) KEY_ENTER) {
                    addAddress();
                }
            }
	    });

		Button button = new Button("add to whitelist");
		button.addClickListener(new ClickListener() {
            public void onClick(Widget sender) {
                addAddress();
            }
		});
		HorizontalPanel hp = new HorizontalPanel();
		hp.add(address);
		hp.add(button);
		add(hp);
		fetchTable();
	}
}
