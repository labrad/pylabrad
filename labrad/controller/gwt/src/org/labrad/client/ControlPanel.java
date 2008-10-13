package org.labrad.client;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.labrad.client.JSONTransport.JSONMessageListener;

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
	/**
	 * Information about a server available on a particular node.
	 */
    private static class ServerInfo extends JavaScriptObject {
        protected ServerInfo() {}
        public final native String getName() /*-{ return this[0]; }-*/;
        public final native String getDescription() /*-{ return this[1]; }-*/;
        public final native String getVersion() /*-{ return this[2]; }-*/;
        public final native String getInstanceName() /*-{ return this[3]; }-*/;
        public final native JsArray<String> getEnvironmentVars() /*-{ return this[4]; }-*/;
        public final native JsArray<String> getInstances() /*-{ return this[5]; }-*/;
    }
    
    /**
     * Message structure for status messages.
     */
    private static class StatusMessage extends JavaScriptObject {
        protected StatusMessage() {}
        public final native String getNode() /*-{ return this["node"]; }-*/;
        public final native JsArray<ServerInfo> getServers() /*-{ return this["servers"]; }-*/;
    }
    
    private final static NodeImageBundle images = (NodeImageBundle)GWT.create(NodeImageBundle.class);
    
    // instance variables
    private Grid table = null;
    private JSONTransport transport;
    private List<String> nodes;
    private List<String> servers;
    private Map<String, Map<String, InstanceController>> controllers;
    
    public ControlPanel(JSONTransport transport) {
        this.transport = transport;
        nodes = new ArrayList<String>();
        servers = new ArrayList<String>();
        controllers = new HashMap<String, Map<String, InstanceController>>();
        updateStatus();
        // listener for status update messages
        transport.addMessageListener("node.status", new JSONMessageListener() {
			public void onMessage(JavaScriptObject args, JavaScriptObject kw) {
				StatusMessage msg = kw.cast();
				String node = msg.getNode();
				List<ServerInfo> servers = JsArray.toList(msg.getServers());
				updateNodeStatus(node, servers);
				makeTable();
			}
        });
        // listener for server disconnect messages
        transport.addMessageListener("Server Disconnected",	new JSONMessageListener() {
			public void onMessage(JavaScriptObject args, JavaScriptObject kw) {
				String name = ((JsObject)kw).getString("name");
			    if (nodeExists(name)) {
			    	removeNode(name);
			    }
			}
        });
    }
    
    /**
     * Fetch the current status of all running nodes.
     */
    public void updateStatus() {
        transport.invokeMethod("status", new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable exception) {
                //resp.setText("Request failed with an error: " + exception.toString());
            }

            @SuppressWarnings("unchecked")
			public void onResponseReceived(JavaScriptObject response) {
            	JsMap<String, JsArray<ServerInfo>> resp = response.cast();
            	nodes.clear();
            	servers.clear();
            	controllers.clear();
            	for (String node : JsMap.keyList(resp)) {
            		updateNodeStatus(node, JsArray.toList(resp.get(node)));
            	}
            	makeTable();
            }
        });
    }
    
    /**
     * Update the status of servers available on a single node.
     * @param node
     * @param servers
     */
    private void updateNodeStatus(String node, List<ServerInfo> servers) {
     	if (!nodeExists(node)) {
     		int i = 0;
     		while ((i < nodes.size()) && (node.compareTo(nodes.get(i))) > 0) i++; 
     		nodes.add(i, node);
     	}
        controllers.put(node, new HashMap<String, InstanceController>());
        for (ServerInfo info : servers) {
        	String server = info.getName();
        	updateServerInfo(node, server, info);
        }
    }
    
    private void removeNode(String node) {
    	nodes.remove(node);
    	controllers.remove(node);
    	makeTable();
    }
    
    /**
     * Update info about a certain server on a certain node.
     * @param node
     * @param server
     * @param info
     */
    private void updateServerInfo(String node, String server, ServerInfo info) {
    	if (!serverExists(server)) {
    		int i = 0;
    		while ((i < servers.size()) && (server.compareTo(servers.get(i))) > 0) i++;
    		servers.add(i, server);
    	}
    	InstanceController ic = new InstanceController(
    		this, transport, node, server,
    		info.getInstanceName(), info.getVersion(), true,
    		JsArray.toList(info.getInstances()),
    		JsArray.toList(info.getEnvironmentVars()));
    	controllers.get(node).put(server, ic);
    }
    
    /**
     * Recreate the control panel table.
     * @param servers
     * @param nodes
     * @param info
     */
    public void makeTable() {
    	// remove servers that are no longer available on any node
        List<String> removals = new ArrayList<String>();
        for (String server : servers) {
        	int count = 0;
        	for (String node : nodes) {
        		if (controllers.get(node).containsKey(server)) {
        			count += 1;
        		}
        	}
        	if (count == 0) removals.add(server);
        }
        for (String server : removals) {
        	servers.remove(server);
        }
        // create the new table widget
    	Grid table = new Grid(servers.size()+1, nodes.size()+1);
        int row, col;
        // create node controls in the column headers
        for (col = 0; col < nodes.size(); col++) {
        	table.setText(0, col+1, nodes.get(col));
            table.setWidget(0, col+1, makeNodeControl(nodes.get(col)));
            table.getCellFormatter().setAlignment(0, col+1,
            		HasHorizontalAlignment.ALIGN_CENTER,
            		HasVerticalAlignment.ALIGN_MIDDLE);
            table.getCellFormatter().addStyleName(0, col+1, "padded-cell");
        }
        // add server names for the row headers
        for (row = 0; row < servers.size(); row++) {
            table.setText(row+1, 0, servers.get(row));
            if (row % 2 == 0) {
            	table.getCellFormatter().addStyleName(row+1, 0, "odd-row");
            }
        }
        // add instance controllers for available servers
        for (row = 0; row < servers.size(); row++) {
            String server = servers.get(row);
            for (col = 0; col < nodes.size(); col++) {
                String node = nodes.get(col);
                if (controllers.get(node).containsKey(server)) {
                	InstanceController ic = controllers.get(node).get(server);
                	table.setWidget(row+1, col+1, ic);
                	table.getCellFormatter().addStyleName(row+1, col+1, "padded-cell");
                }
                if (row % 2 == 0) {
                	table.getCellFormatter().addStyleName(row+1, col+1, "odd-row");
                }
            }
        }
        // update controllers of singleton servers in case they are running elsewhere
        List<String> running = new ArrayList<String>();
        for (String server : servers) {
        	int count = 0;
        	for (String node : nodes) {
        		if (controllers.get(node).containsKey(server)) {
        			InstanceController ic;
        			ic = controllers.get(node).get(server);
        			if (ic.isRunning()) count += 1;
        		}
        	}
        	if (count > 0) running.add(server);
        }
        for (String node: nodes) {
        	Map<String, InstanceController> servers = controllers.get(node);
	        for (String server : running) {
	        	if (servers.containsKey(server)) {
	        		InstanceController ic = servers.get(server);
	        		if (!ic.isRunning()) ic.setRunningElsewhere(true);
	        	}
	        }
        }
        // remove the previous table if necessary
        if (this.table != null) {
    		remove(this.table);
    	}
        this.table = table;
        add(table);
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
    	b.setTitle("Update the list of available servers");
    	b.addClickListener(new ClickListener() {
			public void onClick(Widget sender) {
				b.setEnabled(false);
				JSONArray args = new JSONArray();
				args.set(0, new JSONString(nodename));
				transport.invokeMethod("refresh_servers", args, new JSONTransport.JSONRequestCallback() {
					public void onError(Throwable error) {
						b.setEnabled(true);
					}

					public void onResponseReceived(JavaScriptObject response) {
						b.setEnabled(true);
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
     * Called when the state changes for a particular server.  This message
     * gets sent on to instance controllers on other servers to notify them
     * of the state change, so they can disable or enable themselves accordingly.
     * @param server
     * @param node
     * @param running
     */
    public void serverStateChanged(String server, String node, boolean running) {
        for (String otherNode : nodes) {
        	if (otherNode.equals(node)) continue;
        	Map<String, InstanceController> servers = controllers.get(otherNode);
        	if (servers.containsKey(server)) {
        		servers.get(server).setRunningElsewhere(running);
        	}
        }
    }
    
    /**
     * Lookup the index of the given node in the list
     * @param node
     * @return
     */
    public int lookupNode(String node) {
    	return nodes.indexOf(node);
    }
    
    /**
     * Check whether the given node exists in the list
     * @param node
     * @return
     */
    public boolean nodeExists(String node) {
    	return nodes.contains(node);
    }
    
    /**
     * Lookup the position of a given server in the list
     * @param server
     * @return
     */
    public int lookupServer(String server) {
        return servers.indexOf(server);
    }
    
    /**
     * Check whether the given server exists in the list
     * @param server
     * @return
     */
    public boolean serverExists(String server) {
    	return servers.contains(server);
    }
}
