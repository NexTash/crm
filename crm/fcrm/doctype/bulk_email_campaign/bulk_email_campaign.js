frappe.ui.form.on("Bulk Email Campaign", {
	setup(frm) {
		frm.set_query("sender_account", () => ({ filters: { enable_outgoing: 1 } }));
	},
    
	onload(frm) {
		frm.trigger("load_email_fields");
		frm.trigger("load_filter_builder");
	},

	reference_doctype(frm) {
		frm.set_value("email_field", "");
		frm.set_value("filters_json", "[]");
		frm.trigger("load_email_fields");
		frm.trigger("load_filter_builder");
	},

	load_email_fields(frm) {
		if (!frm.doc.reference_doctype) return;
		frappe
			.call({
				method: "crm.api.bulk_email_campaign.get_email_fields",
				args: { reference_doctype: frm.doc.reference_doctype },
			})
			.then(({ message }) => {
				const options = (message || []).map((field) => ({
					label: field.label,
					value: field.fieldname,
				}));
				frm.set_df_property(
					"email_field",
					"options",
					options.map((x) => x.value).join("\n"),
				);
				frm.set_df_property(
					"email_field",
					"description",
					options.map((x) => `${x.value}: ${x.label}`).join("<br>"),
				);
			});
	},

	load_filter_builder(frm) {
		const wrapper = frm.fields_dict.filter_builder && frm.fields_dict.filter_builder.$wrapper;
		if (!wrapper || !frm.doc.reference_doctype) {
			if (wrapper) wrapper.empty();
			frm.bulk_filter_group = null;
			frm.bulk_filter_doctype = null;
			return;
		}
		if (frm.bulk_filter_group && frm.bulk_filter_doctype === frm.doc.reference_doctype) return;
		frm.bulk_filter_load_id = (frm.bulk_filter_load_id || 0) + 1;
		const load_id = frm.bulk_filter_load_id;
		frm.bulk_filter_group = null;
		wrapper.empty();
		frappe.model.with_doctype(frm.doc.reference_doctype, () => {
			if (load_id !== frm.bulk_filter_load_id) return;
			const saved = frm.doc.filters_json ? JSON.parse(frm.doc.filters_json) : [];
			frm.bulk_filter_group = new frappe.ui.FilterGroup({
				parent: wrapper,
				doctype: frm.doc.reference_doctype,
				on_change: () =>
					frm.set_value(
						"filters_json",
						JSON.stringify(frm.bulk_filter_group.get_filters()),
					),
			});
			frm.bulk_filter_doctype = frm.doc.reference_doctype;
			frm.bulk_filter_group.add_filters_to_filter_group(saved);
		});
	},

	refresh(frm) {
		if (frm.doc.status === "Completed") return;
		const label =
			frm.doc.status === "Running"
				? __("Pause Campaign")
				: frm.doc.status === "Paused"
					? __("Resume Campaign")
					: __("Start Campaign");
		frm.add_custom_button(label, () => {
			if (frm.is_new()) {
				frappe.msgprint(__("Save the campaign before starting it."));
				return;
			}
			const status = frm.doc.status === "Running" ? "Paused" : "Running";
			const method =
				frm.doc.status === "Draft"
					? "crm.api.bulk_email_campaign.start_campaign"
					: "crm.api.bulk_email_campaign.set_campaign_status";
			const args = method.endsWith("start_campaign")
				? { name: frm.doc.name }
				: { name: frm.doc.name, status };
			frappe
				.call({
					method,
					args,
					freeze: true,
					freeze_message: __("Preparing the first email batch..."),
				})
				.then(() => frm.reload_doc());
		});
		frm.add_custom_button(__("Preview Recipients"), () => frm.trigger("preview_recipients"));
	},

	preview_recipients(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Please save the campaign before previewing recipients."));
			return;
		}

		frappe
			.call({
				method: "crm.api.bulk_email_campaign.preview_recipients",
				args: { name: frm.doc.name },
				freeze: true,
			})
			.then(({ message }) => {
				const rows = (message.sample || [])
					.map(
						(row) =>
							`<tr><td>${frappe.utils.escape_html(row.email)}</td><td>${frappe.utils.escape_html(row.reference_name)}</td></tr>`,
					)
					.join("");
				const html = `<p><b>${__("Matching records")}:</b> ${message.total} &nbsp; <b>${__("Valid")}:</b> ${message.valid} &nbsp; <b>${__("Invalid")}:</b> ${message.invalid} &nbsp; <b>${__("Duplicates")}:</b> ${message.duplicates}</p><table class="table table-bordered"><thead><tr><th>${__("Email")}</th><th>${__("Reference")}</th></tr></thead><tbody>${rows}</tbody></table>`;
				frappe.msgprint({ title: __("Preview Recipients"), message: html, wide: true });
			});
	},
});
