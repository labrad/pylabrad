package org.labrad.client;

import com.google.gwt.user.client.ui.AbstractImagePrototype;
import com.google.gwt.user.client.ui.ImageBundle;

public interface NodeImageBundle extends ImageBundle {
	/**
     * Server information.
     */
	@Resource("org/labrad/public/information.gif")
    public AbstractImagePrototype serverInfoIcon();
    
    /**
     * Server information.
     */
    @Resource("org/labrad/public/information_gray.gif")
    public AbstractImagePrototype serverInfoIconDisabled();
    
	/**
	 * Start a server.
	 */
    @Resource("org/labrad/public/add.gif")
	public AbstractImagePrototype startServerIcon();

	/**
	 * Start a server (button disabled).
	 */
    @Resource("org/labrad/public/add_gray.gif")
	public AbstractImagePrototype startServerIconDisabled();
	

	/**
	 * Restart a server.
	 */
    @Resource("org/labrad/public/arrow_refresh.gif")
	public AbstractImagePrototype restartServerIcon();

	/**
	 * Restart a server (button disabled).
	 */
    @Resource("org/labrad/public/arrow_refresh_gray.gif")
	public AbstractImagePrototype restartServerIconDisabled();

	
	/**
	 * Stop a server.
	 */
    @Resource("org/labrad/public/delete.gif")
	public AbstractImagePrototype stopServerIcon();

	/**
	 * Stop a server (button disabled).
	 */
    @Resource("org/labrad/public/delete_gray.gif")
	public AbstractImagePrototype stopServerIconDisabled();
}
