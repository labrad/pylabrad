package org.labrad.client;

import java.util.ArrayList;
import java.util.List;

import com.google.gwt.core.client.GWT;
import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.user.client.ui.ClickListener;
import com.google.gwt.user.client.ui.FlowPanel;
import com.google.gwt.user.client.ui.Grid;
import com.google.gwt.user.client.ui.HasHorizontalAlignment;
import com.google.gwt.user.client.ui.HasVerticalAlignment;
import com.google.gwt.user.client.ui.HorizontalPanel;
import com.google.gwt.user.client.ui.Image;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.PushButton;
import com.google.gwt.user.client.ui.Widget;

public class ControlPanel extends FlowPanel {
    private static class ServerInfo extends JavaScriptObject {
        protected ServerInfo() {}
        public final native boolean isAvailable() /*-{ return this[0]; }-*/;        
        public final native String getDescription() /*-{ return this[1]; }-*/;
        public final native String getVersion() /*-{ return this[2]; }-*/;
        public final native String getInstanceName() /*-{ return this[3]; }-*/;
        public final native JsArray<String> getEnvironmentVars() /*-{ return this[4]; }-*/;
        public final native JsArray<String> getInstances() /*-{ return this[5]; }-*/;
    }
    
    private static class InfoResponse extends JavaScriptObject {
        protected InfoResponse() {}
        public final native JsArray<String> getServers() /*-{ return this[0]; }-*/;
        public final native JsArray<String> getNodes() /*-{ return this[1]; }-*/;
        public final native JsArray<JsArray<ServerInfo>> getServerInfo() /*-{ return this[2]; }-*/;
    }
    
    private final static NodeImageBundle images = (NodeImageBundle)GWT.create(NodeImageBundle.class);
    
    /**
     * Fetch the current status of all running nodes.
     */
    public void fetchTable() {
        transport.invokeMethod("status", new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable exception) {
                //resp.setText("Request failed with an error: " + exception.toString());
            }

            public void onResponseReceived(JavaScriptObject response) {
                InfoResponse ir = (InfoResponse) response;
                
                List<String> serverNames = JsArray.toList(ir.getServers());
                List<String> nodeNames = JsArray.toList(ir.getNodes());
                
                JsArray<JsArray<ServerInfo>> jstatus = ir.getServerInfo();
                List<List<ServerInfo>> info = new ArrayList<List<ServerInfo>>();
                for (int row = 0; row < jstatus.size(); row++) {
                	info.add(JsArray.toList(jstatus.get(row)));
                }
                makeTable(serverNames, nodeNames, info);
            }
        });
    }
    
    /**
     * Make a controller widget for a single node.
     * The controller widget allows the user to trigger a refresh of the
     * server list on this node.
     * @param nodename
     * @return
     */
    private Widget makeNodeControl(final String nodename) {
    	final PushButton b = new PushButton(images.restartServerIcon().createImage());
    	b.getUpDisabledFace().setImage(new Image("throbber.gif"));
    	b.addClickListener(new ClickListener() {
			public void onClick(Widget sender) {
				b.setEnabled(false);
				JSONArray args = new JSONArray();
				args.set(0, new JSONString(nodename));
				transport.invokeMethod("refresh_servers", args, new JSONTransport.JSONRequestCallback() {
					public void onError(Throwable error) {
						b.setEnabled(true);
						fetchTable();
					}

					public void onResponseReceived(JavaScriptObject response) {
						b.setEnabled(true);
						fetchTable();
					}
				});
			}
    	});
    	HorizontalPanel p = new HorizontalPanel();
    	p.add(new Label(nodename));
    	p.add(b);
    	return p;
    }
    
    /**
     * Create the control panel table from the given server information.
     * @param servers
     * @param nodes
     * @param info
     */
    public void makeTable(List<String> servers, List<String> nodes, List<List<ServerInfo>> info) {
    	if (table != null) {
    		remove(table);
    	}
        table = new Grid(servers.size()+1, nodes.size()+1);
        
        int row, col;
        
        for (col = 0; col < nodes.size(); col++) {
            table.setWidget(0, col+1, makeNodeControl(nodes.get(col)));
            table.getCellFormatter().setAlignment(0, col+1,
            		HasHorizontalAlignment.ALIGN_RIGHT,
            		HasVerticalAlignment.ALIGN_MIDDLE);
            table.getCellFormatter().addStyleName(0, col+1, "padded-cell");
        }
        for (row = 0; row < servers.size(); row++) {
            table.setText(row+1, 0, servers.get(row));
        }
        for (row = 0; row < servers.size(); row++) {
            // create a control for each instance
            String server = servers.get(row);
            for (col = 0; col < nodes.size(); col++) {
                String node = nodes.get(col);
                ServerInfo si = info.get(row).get(col);
                InstanceController ic = new InstanceController(this, transport,
                        node, server, si.getInstanceName(), si.getVersion(), si.isAvailable(),
                        JsArray.toList(si.getInstances()), JsArray.toList(si.getEnvironmentVars()));
                table.setWidget(row+1, col+1, ic);
                table.getCellFormatter().addStyleName(row+1, col+1, "padded-cell");
            }
        }
        add(table);
    }
    
    public void addNode(String node) {
    	// add node to the table
    }
    
    private void addServer(String server, String node, ServerInfo info) {
    	// add server to the table
    }
    
    /**
     * Called when the state changes for a particular server.  This message
     * gets sent on to instance controllers on other servers to notify them
     * of the state change, so they can disable or enable themselves accordingly.
     * @param server
     * @param node
     * @param running
     */
    public void serverStateChanged(String server, String node, boolean running) {
        int row = lookupServer(server);
        int n = lookupNode(node);
        for (int col = 0; col < table.getColumnCount() - 1; col++) {
            if (col != n) {
                Widget w = table.getWidget(row+1, col+1);
                if (w != null) {
                    InstanceController ic = (InstanceController)w;
                    ic.setRunningElsewhere(running);
                }
            }
        }
    }
    
    /**
     * Lookup the position of a given server in the list
     * @param server
     * @return
     */
    public int lookupServer(String server) {
        int n = table.getRowCount() - 1;
        for (int i = 0; i < n; i++) {
            if (table.getText(i+1, 0).equals(server)) {
                return i;
            }
        }
        throw new RuntimeException("Server not found: " + server);
    }
    
    /**
     * Check whether the given server exists in the list
     * @param server
     * @return
     */
    public boolean serverExists(String server) {
    	try {
    		lookupServer(server);
    		return true;
    	} catch (Exception e) {
    		return false;
    	}
    }
    
    /**
     * Lookup the index of the given node in the list
     * @param node
     * @return
     */
    public int lookupNode(String node) {
        int n = table.getColumnCount() - 1;
        for (int i = 0; i < n; i++) {
            if (table.getText(0, i+1).equals(node)) {
                return i;
            }
        }
        throw new RuntimeException("Node not found: " + node);
    }
    
    /**
     * Check whether the given node exists in the list
     * @param node
     * @return
     */
    public boolean nodeExists(String node) {
        try {
        	lookupNode(node);
        	return true;
        } catch (Exception e) {
        	return false;
        }
    }
    
    private Grid table = null;
    private JSONTransport transport;
    
    public ControlPanel(JSONTransport transport) {
        this.transport = transport;
        fetchTable();
    }
}
