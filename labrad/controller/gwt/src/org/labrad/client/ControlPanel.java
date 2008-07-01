package org.labrad.client;

import java.util.ArrayList;
import java.util.List;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.user.client.ui.FlowPanel;
import com.google.gwt.user.client.ui.Grid;
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
    
    public void makeTable(List<String> servers, List<String> nodes, List<List<ServerInfo>> info) {
        table = new Grid(servers.size()+1, nodes.size()+1);
        
        int row, col;
        
        for (col = 0; col < nodes.size(); col++) {
            table.setText(0, col+1, nodes.get(col));
            table.getCellFormatter().addStyleName(0, col+1, "centered-cell");
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
