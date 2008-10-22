package org.labrad.client;

import com.google.gwt.user.client.ui.Composite;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.VerticalPanel;

public class LogMessage extends Composite {
	public LogMessage(String message) {
		VerticalPanel p = new VerticalPanel();
		for (String line : message.split("\n")) {
			p.add(new Label(line));
		}
		initWidget(p);
	}
}
