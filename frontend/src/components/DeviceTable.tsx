import {
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Space, Table, Tag } from "antd";
import type { Device, DeviceStatus } from "../api/mappers";
import { statusMeta } from "./deviceMeta";

type DeviceTableProps = {
  devices: Device[];
  checking: boolean;
  onCheck: (device?: Device) => void;
  onEdit: (device: Device) => void;
  onRemove: (device: Device) => void;
};

export function DeviceTable({
  devices,
  checking,
  onCheck,
  onEdit,
  onRemove,
}: DeviceTableProps) {
  const columns = [
    {
      title: "設備",
      dataIndex: "name",
      key: "name",
      render: (name: string, device: Device) => (
        <div className="device-name">
          <strong>{name}</strong>
          <span>
            {device.ip}:{device.port}
          </span>
        </div>
      ),
    },
    {
      title: "讀取設定",
      key: "definition",
      render: (_: unknown, device: Device) => (
        <span className="definition">
          FC {device.function} · {device.address === 0 ? "40001" : device.address} · {" "}
          {device.quantity} 筆
        </span>
      ),
    },
    {
      title: "Unit ID",
      dataIndex: "unit_id",
      key: "unit_id",
    },
    {
      title: "狀態",
      dataIndex: "status",
      key: "status",
      render: (status: DeviceStatus, device: Device) => (
        <div>
          <Tag color={statusMeta[status].color}>{statusMeta[status].label}</Tag>
          <span className="status-detail">{device.error || device.lastChecked}</span>
        </div>
      ),
    },
    {
      title: "值",
      dataIndex: "values",
      key: "values",
      render: (values?: Array<number | boolean>) =>
        values?.length ? values.join(", ") : "—",
    },
    {
      title: "耗時",
      dataIndex: "elapsedMs",
      key: "elapsedMs",
      render: (value?: number) => (value ? `${value} ms` : "—"),
    },
    {
      title: "",
      key: "actions",
      align: "right" as const,
      render: (_: unknown, device: Device) => (
        <Space size={4}>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            loading={checking}
            onClick={() => onCheck(device)}
            aria-label={`檢查 ${device.name}`}
          />
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => onEdit(device)}
            aria-label={`編輯 ${device.name}`}
          />
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={() => onRemove(device)}
            aria-label={`刪除 ${device.name}`}
          />
        </Space>
      ),
    },
  ];

  return (
    <Table
      rowKey="name"
      columns={columns}
      dataSource={devices}
      pagination={{
        pageSize: 50,
        hideOnSinglePage: true,
        showSizeChanger: false,
      }}
      scroll={{ x: 700 }}
    />
  );
}
