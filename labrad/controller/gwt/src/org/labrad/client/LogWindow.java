package org.labrad.client;

import com.google.gwt.user.client.ui.Button;
import com.google.gwt.user.client.ui.ClickListener;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.VerticalPanel;
import com.google.gwt.user.client.ui.Widget;

public class LogWindow extends VerticalPanel {
	private VerticalPanel logger;
	
	private int LOG_LENGTH = 10;
	
	public LogWindow() {
		Button btn = new Button("clear log");
		btn.addClickListener(new ClickListener() {
			public void onClick(Widget sender) {
				clear();
			}			
		});
		logger = new VerticalPanel();
		add(btn);
		add(logger);
	}
	
	public void clear() {
		logger.clear();
	}
	
	public void log(String message) {
		logger.insert(new Label(message), 0);
		if (logger.getWidgetCount() > LOG_LENGTH) {
			logger.remove(logger.getWidgetCount() - 1);
		}
	}
}
