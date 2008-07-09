package org.labrad.client;

import java.util.List;

import com.google.gwt.core.client.GWT;
import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.user.client.ui.ClickListener;
import com.google.gwt.user.client.ui.DeckPanel;
import com.google.gwt.user.client.ui.HasHorizontalAlignment;
import com.google.gwt.user.client.ui.HorizontalPanel;
import com.google.gwt.user.client.ui.Image;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.PushButton;
import com.google.gwt.user.client.ui.VerticalPanel;
import com.google.gwt.user.client.ui.Widget;

public class InstanceController extends HorizontalPanel {
    private String node;
    private String server;
    private String instance;
    @SuppressWarnings("unused")
	private String version;
    private PushButton info;
    private PushButton start;
    private PushButton stop;
    private PushButton restart;
    private Label statusLabel;
    private DeckPanel stuff;
    private ControlPanel parent;
    private JSONTransport transport;
    private boolean available, running, isLocal;
    
    private final static int BUTTONS = 0;
    private final static int THROBBER = 1;
    
    public enum Color {
        GRAY, GREEN, RED
    }
    private Color color;
    
    public enum Status {
        STOPPED, STARTING, RUNNING, RESTARTING, STOPPING,
        UNAVAILABLE, RUNNING_ELSEWHERE
    }
    
    public final static int UNAVAILABLE = 1;
    public final static int STOPPED = 2;
    public final static int STARTING = 3;
    public final static int RUNNING = 4;
    public final static int RUNNING_ELSEWHERE = 5;
    public final static int RESTARTING = 6;
    public final static int STOPPING = 7;
    private Status currentStatus, prevStatus, nextStatus;
    
    private final static NodeImageBundle images = (NodeImageBundle)GWT.create(NodeImageBundle.class);
    
//    private void showInfoPopup() {
//        PopupPanel pp = new PopupPanel(true);
//        RichTextArea rta = new RichTextArea();
//        rta.setText(version);
//        pp.add(rta);
//        pp.setPopupPosition(info.getAbsoluteLeft(), info.getAbsoluteTop());
//        pp.show();
//    }
    
    public InstanceController(ControlPanel parent, JSONTransport transport,
                              String node, String server, String instance, String version,
                              boolean available, List<String> runningInstances, List<String> environmentVars) {
        this.transport = transport;
        this.parent = parent;
        this.node = node;
        this.server = server;
        if (runningInstances.size() > 0) {
            this.instance = runningInstances.get(0);
        } else {
            this.instance = instance;
        }
        this.version = version;
        this.available = available;
        this.running = runningInstances.size() > 0;
        this.isLocal = environmentVars.size() > 0;
        this.color = Color.GRAY;
        
        info = new PushButton(images.serverInfoIcon().createImage());
        info.getUpDisabledFace().setImage(images.serverInfoIconDisabled().createImage());
        //info.addClickListener(new ClickListener() {
        //    public void onClick(Widget sender) {
        //        showInfoPopup();
        //    }
        //});
        info.setEnabled(version != null);
        info.setTitle(version);
        
        start = new PushButton(images.startServerIcon().createImage());
        start.getUpDisabledFace().setImage(images.startServerIconDisabled().createImage());
        start.addClickListener(new ClickListener() {
            public void onClick(Widget sender) {
                startServer();
            }
        });
        
        stop = new PushButton(images.stopServerIcon().createImage());
        stop.getUpDisabledFace().setImage(images.stopServerIconDisabled().createImage());
        stop.addClickListener(new ClickListener() {
            public void onClick(Widget sender) {
                stopServer();
            }
        });
        
        restart = new PushButton(images.restartServerIcon().createImage());
        restart.getUpDisabledFace().setImage(images.restartServerIconDisabled().createImage());
        restart.addClickListener(new ClickListener() {
            public void onClick(Widget sender) {
                restartServer();
            }
        });
        
        statusLabel = new Label();
        statusLabel.addStyleDependentName("status");

        HorizontalPanel buttons = new HorizontalPanel();
        buttons.add(start);
        buttons.add(stop);
        buttons.add(restart);
        
        VerticalPanel throbber = new VerticalPanel();
        throbber.add(new Image("throbber.gif"));
        throbber.setHorizontalAlignment(HasHorizontalAlignment.ALIGN_CENTER);
        
        stuff = new DeckPanel();
        stuff.add(buttons);
        stuff.add(throbber);
        
        add(statusLabel);
        add(info);
        add(stuff);
        
        if (available) {
            setStatus(running ? Status.RUNNING : Status.STOPPED, false);
        } else {
            setStatus(Status.UNAVAILABLE, false);
        }
    }
    
    private void startStatusChange(Status intermediateStatus, Status finalStatus) {
    	prevStatus = currentStatus;
    	nextStatus = finalStatus;
    	setStatus(intermediateStatus);
    }
    
    private void abortStatusChange() {
    	setStatus(prevStatus);
    }
    
    private void finishStatusChange(String instanceName) {
    	if (instanceName != null) {
    		instance = instanceName;
    	}
    	setStatus(nextStatus);
    }
    
    private void setButtonState(boolean start, boolean restart, boolean stop) {
    	this.start.setEnabled(start);
    	this.restart.setEnabled(restart);
    	this.stop.setEnabled(stop);
    }
    
    private void setColor(Color newColor) {
        switch (color) {
            case GREEN:
                statusLabel.removeStyleDependentName("green");
                break;
                
            case RED:
                statusLabel.removeStyleDependentName("red");
                break;
        }
        switch (newColor) {
            case GREEN:
                statusLabel.addStyleDependentName("green");
                break;
            
            case RED:
                statusLabel.addStyleDependentName("red");
                break;
        }
        color = newColor;
    }
    
    public void setRunningElsewhere(boolean running) {
        if (isLocal || !available) {
        	return;
        }
        setStatus(running ? Status.RUNNING_ELSEWHERE : Status.STOPPED, false);
    }
    
    public void setStatus(Status status) {
        setStatus(status, true);
    }
    
    public void setStatus(Status status, boolean notifyParent) {
    	switch (status) {
    	    case UNAVAILABLE:
    	        setButtonState(false, false, false);
    	        stuff.showWidget(BUTTONS);
    	        statusLabel.setText("unavailable");
    	        setColor(Color.GRAY);
    	        break;
    	        
    		case STOPPED:
    			setButtonState(true, false, false);
    			stuff.showWidget(BUTTONS);
    			statusLabel.setText("stopped");
    			setColor(Color.RED);
    			if (notifyParent && status != currentStatus) {
    			    parent.serverStateChanged(server, node, false);
    			}
    			break;
    			
    		case STARTING:
    			setButtonState(false, false, false);
    			stuff.showWidget(THROBBER);
    			statusLabel.setText("starting...");
    			setColor(Color.RED);
    			break;
    			
    		case RUNNING:
    			setButtonState(false, true, true);
    			stuff.showWidget(BUTTONS);
    			statusLabel.setText("started");
    			setColor(Color.GREEN);
    			if (notifyParent && status != currentStatus) {
    			    parent.serverStateChanged(server, node, true);
    			}
    			break;
    			
    		case RUNNING_ELSEWHERE:
                setButtonState(false, false, false);
                stuff.showWidget(BUTTONS);
                statusLabel.setText("started");
                setColor(Color.GRAY);
                break;
    			
    		case RESTARTING:
    			setButtonState(false, false, false);
    			stuff.showWidget(THROBBER);
    			statusLabel.setText("restarting...");
    			break;
    			
    		case STOPPING:
    			setButtonState(false, false, false);
    			stuff.showWidget(THROBBER);
    			statusLabel.setText("stopping...");
    			break;
    	}
    	currentStatus = status;
    }
    
    public void startServer() {
    	callRemote("start", server, Status.STARTING, Status.RUNNING);
    }
    
    public void restartServer() {
    	callRemote("restart", instance, Status.RESTARTING, Status.RUNNING);
    }
    
    public void stopServer() {
    	callRemote("stop", instance, Status.STOPPING, Status.STOPPED);
    }
    
    private void callRemote(String method, String server, Status intermediateStatus, Status nextStatus) {
        JSONArray args = new JSONArray();
        args.set(0, new JSONString(node));
        args.set(1, new JSONString(server));
        
        startStatusChange(intermediateStatus, nextStatus);
        transport.invokeMethod(method, args, new JSONTransport.JSONRequestCallback() {
            public void onError(Throwable exception) {
                abortStatusChange();
            }
            
            public void onResponseReceived(JavaScriptObject response) {
                String instanceName = ((JsString)response).toString();
                finishStatusChange(instanceName);
            }
        });
    }
}
