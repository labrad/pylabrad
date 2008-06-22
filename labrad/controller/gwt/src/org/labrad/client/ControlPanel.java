package org.labrad.client;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONBoolean;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.json.client.JSONValue;
import com.google.gwt.user.client.ui.FlowPanel;
import com.google.gwt.user.client.ui.Grid;
import com.google.gwt.user.client.ui.Widget;

public class ControlPanel extends FlowPanel {
    private static class ServerInfo extends JavaScriptObject {
        protected ServerInfo() {
        }
    
        public final native String getInstanceName() /*-{
            return this[0];
        }-*/;
    
        public final native String getVersion() /*-{
            return this[1];
        }-*/;
        
        public final native boolean isAvailable() /*-{
            return this[2];
        }-*/;
    
        public final native boolean isRunning() /*-{
            return this[3];
        }-*/;
        
        public final native boolean isLocal() /*-{
            return this[4];
        }-*/;
        
    }
    
    private static class InfoResponse extends JavaScriptObject {
        protected InfoResponse() {
        }
        
        public final native JsArray<String> getServers() /*-{
            return this[0];
        }-*/;
        
        public final native JsArray<String> getNodes() /*-{
            return this[1];
        }-*/;
        
        public final native JsArray<JsArray<ServerInfo>> getServerInfo() /*-{
            return this[2];
        }-*/;
    }
    
    public void fetchTable() {
        transport.invokeMethod("status", new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable exception) {
                //resp.setText("Request failed with an error: " + exception.toString());
            }

            public void onResponseReceived(JavaScriptObject response) {
                
                InfoResponse ir = (InfoResponse) response;
                
                JsArray<String> jservers = ir.getServers();
                String[] serverNames = new String[jservers.size()];
                for (int i = 0; i < jservers.size(); i++) {
                    serverNames[i] = jservers.get(i);
                }
                
                JsArray<String> jnodes = ir.getNodes();
                String[] nodeNames = new String[jnodes.size()];
                for (int i = 0; i < jnodes.size(); i++) {
                    nodeNames[i] = jnodes.get(i);
                }
                
                JsArray<JsArray<ServerInfo>> jstatus = ir.getServerInfo();
                JsArray<ServerInfo> rowarry = jstatus.get(0);
                ServerInfo[][] info = new ServerInfo[jstatus.size()][rowarry.size()];
                
                for (int row = 0; row < jstatus.size(); row++) {
                    rowarry = jstatus.get(row);
                    for (int col = 0; col < rowarry.size(); col++) {
                        info[row][col] = rowarry.get(col);
                    }
                }
                
                makeTable(serverNames, nodeNames, info);
            }
        });
    }
    
    public void makeTable(String[] servers, String[] nodes, ServerInfo[][] info) {
        table = new Grid(servers.length+1, nodes.length+1);
        
        int row, col;
        
        for (col = 0; col < nodes.length; col++) {
            table.setText(0, col+1, nodes[col]);
            table.getCellFormatter().addStyleName(0, col+1, "centered-cell");
        }
        for (row = 0; row < servers.length; row++) {
            table.setText(row+1, 0, servers[row]);
        }
        for (row = 0; row < servers.length; row++) {
            // create a control for each instance
            String server = servers[row];
            for (col = 0; col < nodes.length; col++) {
                String node = nodes[col];
                ServerInfo si = info[row][col];
                InstanceController ic = new InstanceController(this, transport,
                        node, server, si.getInstanceName(), si.getVersion(),
                        si.isAvailable(), si.isRunning(), si.isLocal());
                table.setWidget(row+1, col+1, ic);
                table.getCellFormatter().addStyleName(row+1, col+1, "padded-cell");
            }
        }
        add(table);
    }
    
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
    
    public int lookupServer(String server) {
        int n = table.getRowCount() - 1;
        for (int i = 0; i < n; i++) {
            if (table.getText(i+1, 0).equals(server)) {
                return i;
            }
        }
        throw new RuntimeException("Server not found: " + server);
    }
    
    public int lookupNode(String node) {
        int n = table.getColumnCount() - 1;
        for (int i = 0; i < n; i++) {
            if (table.getText(0, i+1).equals(node)) {
                return i;
            }
        }
        throw new RuntimeException("Node not found: " + node);
    }
    
    private Grid table = null;
    private JSONTransport transport;
  
    public ControlPanel(JSONTransport transport) {
        this.transport = transport;
        fetchTable();
    }
}
