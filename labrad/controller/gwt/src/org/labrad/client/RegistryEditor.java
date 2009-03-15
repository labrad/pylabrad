package org.labrad.client;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.labrad.client.JSONTransport.JSONRequestCallback;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.json.client.JSONArray;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.user.client.ui.Composite;
import com.google.gwt.user.client.ui.Tree;
import com.google.gwt.user.client.ui.TreeItem;
import com.google.gwt.user.client.ui.TreeListener;

public class RegistryEditor extends Composite implements TreeListener {
	private final Tree tree;
	private final JSONTransport transport;
	private final Map<String, TreeItem> dirs;
	
	class ItemInfo {
		public Map<String, TreeItem> dirs;
		public List<String> path;
		public ItemInfo(List<String> path, String dir) {
			dirs = new HashMap<String, TreeItem>();
			this.path = new ArrayList<String>();
			this.path.addAll(path);
			this.path.add(dir);
		}
	}
	
	public RegistryEditor(JSONTransport transport) {
		this.transport = transport;
		tree = new Tree();
		tree.addTreeListener(this);
		tree.setAnimationEnabled(true);
		dirs = new HashMap<String, TreeItem>();
		initWidget(tree);
		loadDirectory(new ArrayList<String>());
	}
	
	private void loadDirectory(List<String> path) {
		path.add(0, "");
		final JSONArray jpath = new JSONArray();
		for (int i = 0; i < path.size(); i++) {
			jpath.set(i, new JSONString(path.get(i)));
		}
		JSONArray args = new JSONArray();
		args.set(0, jpath);
		transport.invokeMethod("registry_dir", args, new JSONRequestCallback() {
			public void onError(Throwable error) {
				// handle errors
				tree.addItem("error!");
			}

			public void onResponseReceived(JavaScriptObject response) {
				JsArray<JsArray<String>> info = response.cast();
				List<String> dirs = JsArray.toList(info.get(0));
				List<String> keys = JsArray.toList(info.get(1));
				List<String> path = new ArrayList<String>();
				for (int i = 1; i < jpath.size(); i++) {
					path.add(((JSONString)jpath.get(i)).stringValue());
				}
				populateTree(path, dirs, keys);
			}
		});

	}
	
	private void populateTree(List<String> path, List<String> dirs, List<String> keys) {
		TreeItem item;
		List<TreeItem> oldItems = new ArrayList<TreeItem>();
		if (path.size() == 0) {
			for (int i = 0; i < tree.getItemCount(); i++) {
				oldItems.add(tree.getItem(i));
			}
			this.dirs.clear();
			for (String dir : dirs) {
				item = new TreeItem(dir);
				item.setUserObject(new ItemInfo(path, dir));
				item.addItem("");
				this.dirs.put(dir, item);
				tree.addItem(item);
			}
			for (String key : keys) {
				item = new TreeItem(key);
				tree.addItem(item);
			}
			for (TreeItem oldItem : oldItems) {
				tree.removeItem(oldItem);
			}
		} else {
			TreeItem parent = lookupItem(path);
			for (int i = 0; i < parent.getChildCount(); i++) {
				oldItems.add(parent.getChild(i));
			}
			Map<String, TreeItem> dirMap = ((ItemInfo)parent.getUserObject()).dirs;
			dirMap.clear();
			for (String dir : dirs) {
				item = new TreeItem(dir);
				item.setUserObject(new ItemInfo(path, dir));
				item.addItem("");
				dirMap.put(dir, item);
				parent.addItem(item);
			}
			for (String key : keys) {
				item = new TreeItem(key);
				parent.addItem(item);
			}
			for (TreeItem oldItem : oldItems) {
				tree.removeItem(oldItem);
			}
		}
	}
	
	private TreeItem lookupItem(List<String> path) {
		Map<String, TreeItem> dirs = this.dirs;
		TreeItem item = null;
		for (String dir : path) {
			item = dirs.get(dir);
			dirs = ((ItemInfo)item.getUserObject()).dirs;
		}
		return item;
	}
	
	public void onTreeItemSelected(TreeItem item) {
	}

	public void onTreeItemStateChanged(TreeItem item) {
		if (item.getState()) {
			Object obj = item.getUserObject();
			List<String> path = ((ItemInfo)obj).path;
			loadDirectory(path);
		}
	}
	
	
}
