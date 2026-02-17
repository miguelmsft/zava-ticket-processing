import type { Priority } from '../types/ticket'

export interface SampleTicket {
  title: string
  description: string
  tags: string
  priority: Priority
  submitter: string
  submitterName: string
  submitterDepartment: string
  pdfFilename: string
  scenario: string
  scenarioLabel: string
}

export const SAMPLE_TICKETS: SampleTicket[] = [
  {
    title: 'Invoice Processing Request - ABC Industrial Supplies - Valve Assemblies',
    description:
      'Please process the attached invoice from ABC Industrial Supplies for valve assemblies and seal kits ordered for the Q1 maintenance cycle on Process Line 4. This is a standard reorder under PO-2026-1150. All items have been received and inspected by the warehouse team.',
    tags: 'invoice,vendor-abc,maintenance,process-line-4',
    priority: 'normal',
    submitter: 'john.doe@zavaprocessing.com',
    submitterName: 'John Doe',
    submitterDepartment: 'Procurement',
    pdfFilename: 'INV_ABC_Industrial_2026_78432.pdf',
    scenario: 'happy_path',
    scenarioLabel: '✅ Happy Path — All validations pass',
  },
  {
    title: 'URGENT: Chemical Supply Invoice - Delta Chemical Solutions - Lab Reagents',
    description:
      'Urgent processing needed for Delta Chemical Solutions invoice. These are hazardous chemical reagents required for the quality control lab. The chemicals are needed for the FDA compliance testing scheduled for next week.',
    tags: 'invoice,vendor-delta,urgent,hazardous,lab-supplies,fda-compliance',
    priority: 'urgent',
    submitter: 'maria.garcia@zavaprocessing.com',
    submitterName: 'Maria Garcia',
    submitterDepartment: 'Quality Control',
    pdfFilename: 'INV_Delta_Chemical_2026_DC4410.pdf',
    scenario: 'hazardous_materials',
    scenarioLabel: '⚠️ Hazardous Materials — EHS flags',
  },
  {
    title: 'Invoice Processing Request - Pinnacle Precision Parts - Bearings & Shafts',
    description:
      'Attached is the invoice from Pinnacle Precision Parts for bearings and precision ground shafts for the turbine overhaul project. Note: there may be a pricing error on line item 3.',
    tags: 'invoice,vendor-pinnacle,pricing-discrepancy,turbine-overhaul',
    priority: 'normal',
    submitter: 'robert.chen@zavaprocessing.com',
    submitterName: 'Robert Chen',
    submitterDepartment: 'Maintenance Engineering',
    pdfFilename: 'INV_Pinnacle_Precision_2026_PP7891.pdf',
    scenario: 'amount_discrepancy',
    scenarioLabel: '🔍 Amount Discrepancy → Manual Review',
  },
  {
    title: 'Invoice Processing Request - Summit Electrical Corp - Motor & Panel',
    description:
      'Submitting the invoice from Summit Electrical Corp for the replacement motor and electrical panel upgrades. The invoice is now past due — please process ASAP.',
    tags: 'invoice,vendor-summit,past-due,production-line-2,electrical',
    priority: 'high',
    submitter: 'sarah.williams@zavaprocessing.com',
    submitterName: 'Sarah Williams',
    submitterDepartment: 'Facilities Management',
    pdfFilename: 'INV_Summit_Electrical_2025_SE12088.pdf',
    scenario: 'past_due',
    scenarioLabel: '⏰ Past Due — Expedited payment',
  },
  {
    title: 'Freight Invoice - Oceanic Freight Logistics - Q1 Raw Materials Shipment',
    description:
      'Freight invoice from Oceanic Freight Logistics for the Q1 raw materials shipment. Large multi-container shipment including customs, port handling, and inland transportation.',
    tags: 'invoice,vendor-oceanic,freight,international,q1-materials,multi-line',
    priority: 'normal',
    submitter: 'david.thompson@zavaprocessing.com',
    submitterName: 'David Thompson',
    submitterDepartment: 'Supply Chain',
    pdfFilename: 'INV_Oceanic_Freight_2026_OFL30055.pdf',
    scenario: 'complex_multi_line',
    scenarioLabel: '📦 Complex Multi-Line — 6 items, freight',
  },
  {
    title: 'Invoice Processing Request - Greenfield Environmental Services - Waste Disposal',
    description:
      "Please process the attached invoice from Greenfield Environmental Services for quarterly hazardous waste disposal. Note: I'm not sure if Greenfield is still on our approved vendor list.",
    tags: 'invoice,vendor-greenfield,waste-disposal,environmental,vendor-check',
    priority: 'normal',
    submitter: 'lisa.park@zavaprocessing.com',
    submitterName: 'Lisa Park',
    submitterDepartment: 'Environmental Health & Safety',
    pdfFilename: 'INV_Greenfield_Env_2026_GES2200.pdf',
    scenario: 'unapproved_vendor',
    scenarioLabel: '🚫 Unapproved Vendor → Vendor Approval',
  },
]
