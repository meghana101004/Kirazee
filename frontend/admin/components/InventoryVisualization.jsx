import React, { useState, useMemo, useEffect } from 'react';
import { FaWarehouse, FaChartPie } from 'react-icons/fa';
import '../../css/admin/inventory-visualization.css';

const InventoryVisualization = ({ inventoryData }) => {
  const [hoveredSegment, setHoveredSegment] = useState(null);
  const [animationProgress, setAnimationProgress] = useState(0);

  // Color mapping for categories
  const CATEGORY_PALETTE = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
    '#F7DC6F', '#BB8FCE', '#85C1E2', '#F8B739', '#52C777'
  ];

  function getCategoryColor(category, index) {
    const namedColors = {
      'Beverages': '#FF6B6B',
      'Snacks': '#4ECDC4',
      'Dairy': '#45B7D1',
      'Bakery': '#FFA07A',
      'Groceries': '#98D8C8',
      'Personal Care': '#F7DC6F',
      'Household': '#BB8FCE',
      'Electronics': '#85C1E2',
      'Clothing': '#F8B739',
      'Stationery': '#52C777'
    };

    if (namedColors[category]) {
      return namedColors[category];
    }
    return CATEGORY_PALETTE[index % CATEGORY_PALETTE.length];
  }

  // Process inventory data for visualization
  const processedData = useMemo(() => {
    if (!inventoryData || Object.keys(inventoryData).length === 0) {
      return {
        chartData: [],
        categories: [],
        totalUnits: 0,
        occupiedSpace: 0,
        availableSpace: 100,
        totalCapacity: 0,
        totalOccupied: 0,
        totalAvailable: 0
      };
    }

    // Convert menu category data to visualization format
    const categories = Object.entries(inventoryData).map(([category, count], index) => ({
      name: category,
      value: count,
      percentage: 0, // Will be calculated below
      items: [],
      color: getCategoryColor(category, index)
    }));

    const totalUnits = categories.reduce((sum, cat) => sum + cat.value, 0);

    // Calculate percentages
    if (totalUnits > 0) {
      categories.forEach(cat => {
        cat.percentage = (cat.value / totalUnits) * 100;
      });
    }

    const totalCapacity = totalUnits + Math.ceil(totalUnits * 0.2); // 20% buffer
    const totalOccupied = totalUnits;
    const totalAvailable = totalCapacity - totalOccupied;
    const occupiedSpace = (totalOccupied / totalCapacity) * 100;
    const availableSpace = 100 - occupiedSpace;

    // Add available space as a category
    if (availableSpace > 0) {
      categories.push({
        name: 'Available',
        value: Math.round(availableSpace),
        percentage: availableSpace,
        items: [],
        color: '#e5e7eb'
      });
    }

    return {
      chartData: categories.filter(cat => cat.value > 0),
      categories: categories.filter(cat => cat.name !== 'Available'),
      totalUnits,
      occupiedSpace,
      availableSpace,
      totalCapacity,
      totalOccupied,
      totalAvailable
    };
  }, [inventoryData]);

  // Smooth fill animation on data load/change
  useEffect(() => {
    let frameId;
    let start = null;
    const duration = 1000;

    const animate = (timestamp) => {
      if (start === null) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      setAnimationProgress(progress);
      if (progress < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    setAnimationProgress(0);
    frameId = requestAnimationFrame(animate);

    return () => {
      if (frameId) cancelAnimationFrame(frameId);
    };
  }, [inventoryData]);

  // Create vertical segments for each category
  const createVerticalSegments = () => {
    const segments = [];
    const tubeHeight = 450; // Increased to match Order Status height
    const tubeTopY = 10;
    const tubeWidth = 150;
    const tubeCenterX = 100;
    const tubeX = tubeCenterX - tubeWidth / 2;

    const innerTopY = tubeTopY + 8;
    const innerHeight = tubeHeight - 16;
    const innerBottomY = innerTopY + innerHeight;

    const capacity = processedData.totalCapacity || processedData.totalUnits || 1;
    const occupied = processedData.totalOccupied || processedData.totalUnits || 0;
    const maxUsedHeight = Math.max(0, Math.min(innerHeight, (occupied / capacity) * innerHeight));

    const clampedProgress = Math.max(0, Math.min(animationProgress, 1));
    const usedHeight = maxUsedHeight * clampedProgress;

    const allItems = processedData.chartData
      .filter(category => category.name !== 'Available')
      .map(category => ({
        name: category.name,
        stock: category.value,
        category: category.name,
        color: category.color,
        percentage: category.percentage
      }));

    const totalStock = allItems.reduce((sum, item) => sum + (item.stock || 0), 0);
    if (totalStock <= 0 || usedHeight <= 0) return segments;

    const sortedItems = [...allItems].sort((a, b) => (b.stock || 0) - (a.stock || 0));

    const visibleItems = [];
    let visibleHeightSum = 0;

    sortedItems.forEach(item => {
      if (!item.stock || item.stock <= 0) return;
      const rawHeight = (item.stock / totalStock) * usedHeight;
      if (rawHeight < 2) return;
      visibleItems.push({ item, rawHeight });
      visibleHeightSum += rawHeight;
    });

    if (visibleItems.length === 0) return segments;

    const scale = visibleHeightSum > 0 ? usedHeight / visibleHeightSum : 1;
    let currentY = innerBottomY;

    visibleItems.forEach(({ item, rawHeight }, index) => {
      const height = rawHeight * scale;
      const y = currentY - height;

      segments.push({
        ...item,
        x: tubeX + 2,
        y,
        width: tubeWidth - 4,
        height,
        index,
        tubeTopY: innerTopY,
        tubeBottomY: innerBottomY,
        tubeWidth: tubeWidth - 4,
        tubeCenterX,
        value: item.stock
      });

      currentY = y;
    });

    return segments;
  };

  const verticalSegments = createVerticalSegments();

  const tubeHeight = 450; // Increased to match Order Status height
  const tubeTopY = 10;
  const tubeWidth = 150;
  const tubeCenterX = 100;
  const tubeX = tubeCenterX - tubeWidth / 2;

  if (!inventoryData || Object.keys(inventoryData).length === 0) {
    return (
      <div className="inventory-visualization">
        <div className="no-data-message">
          <FaWarehouse />
          <p>No category data available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="inventory-visualization">
      <div className="visualization-content">
        <div className="charts-container">
          <div className="cylindrical-chart">
            <svg
              viewBox="0 0 200 480"
              preserveAspectRatio="xMidYMid meet"
              className="inventory-tube-svg"
            >
              <defs>
                {processedData.chartData.map((category, index) => (
                  <linearGradient key={`gradient-${index}`} id={`gradient-${index}`} x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor={category.color} stopOpacity={1} />
                    <stop offset="100%" stopColor={category.color} stopOpacity={0.7} />
                  </linearGradient>
                ))}
                <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceAlpha" stdDeviation="3" />
                  <feOffset dx="0" dy="2" result="offsetblur" />
                  <feComponentTransfer>
                    <feFuncA type="linear" slope="0.3" />
                  </feComponentTransfer>
                  <feMerge>
                    <feMergeNode />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Outer tube shell */}
              <g filter="url(#shadow)">
                <rect
                  x={tubeX}
                  y={tubeTopY + 4}
                  width={tubeWidth}
                  height={tubeHeight - 4}
                  rx={0}
                  fill="#f9fafb"
                />
              </g>

              {/* Inner empty space */}
              <rect
                x={tubeX + 4}
                y={tubeTopY + 10}
                width={tubeWidth - 4}
                height={tubeHeight - 20}
                rx={0}
                fill="#ffffff"
              />

              {/* Vertical storage segments */}
              {verticalSegments.map((segment, index) => (
                <g key={index}>
                  <rect
                    x={segment.x + 4}
                    y={segment.y}
                    width={segment.width - 8}
                    height={segment.height}
                    fill={segment.color}
                    stroke="#fff"
                    strokeWidth="1.5"
                    className="storage-segment"
                    onMouseEnter={() => setHoveredSegment(segment)}
                    onMouseLeave={() => setHoveredSegment(null)}
                    rx={0}
                    ry={0}
                    style={{
                      cursor: 'pointer',
                      transform: hoveredSegment?.index === segment.index ? 'scale(1.02)' : 'scale(1)',
                      transformOrigin: `${tubeCenterX}px ${segment.tubeBottomY}px`,
                      transition: 'transform 0.2s ease'
                    }}
                  />
                </g>
              ))}
            </svg>
          </div>

          {/* Tooltip */}
          {hoveredSegment && (
            <div className="chart-tooltip">
              <div className="tooltip-header">
                <div
                  className="tooltip-color"
                  style={{ backgroundColor: hoveredSegment.color }}
                ></div>
                <span className="tooltip-title">{hoveredSegment.name}</span>
              </div>
              <div className="tooltip-content">
                <div className="tooltip-row">
                  <span>Items:</span>
                  <span>{hoveredSegment.value} items</span>
                </div>
                <div className="tooltip-row">
                  <span>Percentage:</span>
                  <span>{Number(hoveredSegment.percentage || 0).toFixed(1)}%</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="category-legend">
          <div className={`legend-items ${processedData.categories.length > 10 ? 'grid-layout' : ''}`}>
            {processedData.categories.map((category, index) => (
              <div key={index} className="legend-item">
                <div
                  className="legend-color"
                  style={{ backgroundColor: category.color }}
                ></div>
                <div className="legend-info">
                  <div className="legend-name">{category.name}</div>
                  <div className="legend-details">
                    <span className="legend-stock">{category.value} items</span>
                    <span className="legend-percentage">({category.percentage.toFixed(1)}%)</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default InventoryVisualization;
